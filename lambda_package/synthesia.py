#!/usr/bin/env python3
"""
Synthesia-like app for violin that creates a video visualization
of notes to play on a violin fingerboard from a musicxml file.
"""

import os
import xml.etree.ElementTree as ET
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import VideoClip # Corrected import for moviepy
# from moviepy import * # Avoid using import *
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Violin string notes (G3, D4, A4, E5)
VIOLIN_STRINGS = ["G", "D", "A", "E"]
STRING_COLORS = [(139, 69, 19), (165, 42, 42), (205, 133, 63), (210, 180, 140)]  # Brown colors for strings
NOTE_COLOR = (0, 191, 255)  # Deep sky blue for notes
HIGHLIGHT_COLOR = (255, 0, 0)  # Red for currently playing note

# Define the fingerboard dimensions
FB_WIDTH = 800
FB_HEIGHT = 300
STRING_SPACING = FB_HEIGHT // 5
FRET_SPACING = FB_WIDTH // 16

# Define the note positions on each string
# This is a simplified mapping of notes to finger positions
NOTE_POSITIONS = {
    # G string (G3 to G5)
    "G3": (0, 0), "G#3": (1, 0), "A3": (2, 0), "A#3": (3, 0), 
    "B3": (4, 0), "C4": (5, 0), "C#4": (6, 0), "D4": (7, 0),
    "D#4": (8, 0), "E4": (9, 0), "F4": (10, 0), "F#4": (11, 0),
    "G4": (12, 0), "G#4": (13, 0), "A4": (14, 0), "A#4": (15, 0),
    
    # D string (D4 to D6)
    "D4": (0, 1), "D#4": (1, 1), "E4": (2, 1), "F4": (3, 1),
    "F#4": (4, 1), "G4": (5, 1), "G#4": (6, 1), "A4": (7, 1),
    "A#4": (8, 1), "B4": (9, 1), "C5": (10, 1), "C#5": (11, 1),
    "D5": (12, 1), "D#5": (13, 1), "E5": (14, 1), "F5": (15, 1),
    
    # A string (A4 to A6)
    "A4": (0, 2), "A#4": (1, 2), "B4": (2, 2), "C5": (3, 2),
    "C#5": (4, 2), "D5": (5, 2), "D#5": (6, 2), "E5": (7, 2),
    "F5": (8, 2), "F#5": (9, 2), "G5": (10, 2), "G#5": (11, 2),
    "A5": (12, 2), "A#5": (13, 2), "B5": (14, 2), "C6": (15, 2),
    
    # E string (E5 to E7)
    "E5": (0, 3), "F5": (1, 3), "F#5": (2, 3), "G5": (3, 3),
    "G#5": (4, 3), "A5": (5, 3), "A#5": (6, 3), "B5": (7, 3),
    "C6": (8, 3), "C#6": (9, 3), "D6": (10, 3), "D#6": (11, 3),
    "E6": (12, 3), "F6": (13, 3), "F#6": (14, 3), "G6": (15, 3),
}

def parse_musicxml(file_path):
    """Parse musicxml file and extract notes with timing information."""
    logging.info(f"Starting MusicXML parsing for: {file_path}")
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
    except ET.ParseError as e:
        logging.error(f"Failed to parse XML file {file_path}: {e}")
        raise
    except FileNotFoundError:
        logging.error(f"MusicXML file not found: {file_path}")
        raise

    notes = []
    current_time = 0  # in seconds
    
    try:
        # Find divisions (ticks per quarter note)
        divisions_elem = root.find('.//divisions')
        if divisions_elem is None or not divisions_elem.text:
            logging.error("Divisions element not found or empty in MusicXML.")
            raise ValueError("Divisions element not found or empty in MusicXML.")
        divisions = float(divisions_elem.text)
        if divisions == 0:
            logging.error("Divisions value cannot be zero.")
            raise ValueError("Divisions value cannot be zero.")

        tempo_bpm = 120 # Default tempo if not specified
        # Try to find tempo, typically in a <sound tempo="X"/> attribute or <metronome> tag
        sound_tempo_elem = root.find('.//sound[@tempo]')
        if sound_tempo_elem is not None and sound_tempo_elem.get('tempo'):
            tempo_bpm = float(sound_tempo_elem.get('tempo'))
        else:
            metronome_elem = root.find('.//metronome/beat-unit-dot/../per-minute') # More complex path
            if metronome_elem is not None and metronome_elem.text:
                tempo_bpm = float(metronome_elem.text)
        
        seconds_per_division = (60.0 / tempo_bpm) / divisions
        logging.info(f"MusicXML properties: Divisions per quarter: {divisions}, Tempo: {tempo_bpm} BPM, Seconds per division: {seconds_per_division:.4f}")

    except ValueError as e:
        logging.error(f"Error parsing initial MusicXML properties: {e}")
        raise

    # Process each measure
    for measure_idx, measure in enumerate(root.findall('.//measure')):
        for note_idx, note_element in enumerate(measure.findall('note')):
            is_grace_note = note_element.find('grace') is not None
            if is_grace_note: # Skip grace notes for now, they don't have standard duration
                logging.debug(f"Skipping grace note in measure {measure_idx+1}")
                continue

            # Skip rests
            if note_element.find('rest') is not None:
                duration_element = note_element.find('duration')
                if duration_element is not None and duration_element.text:
                    try:
                        duration_ticks = float(duration_element.text)
                        current_time += duration_ticks * seconds_per_division
                    except ValueError:
                        logging.warning(f"Invalid duration for rest in measure {measure_idx+1}, note {note_idx+1}. Skipping its time contribution.")
                continue
            
            # Get pitch information
            pitch = note_element.find('pitch')
            if pitch is None:
                logging.debug(f"Skipping note without pitch in measure {measure_idx+1}, note {note_idx+1}")
                continue
                
            step_elem = pitch.find('step')
            octave_elem = pitch.find('octave')

            if step_elem is None or not step_elem.text or octave_elem is None or not octave_elem.text:
                logging.warning(f"Missing step or octave for note in measure {measure_idx+1}, note {note_idx+1}. Skipping note.")
                continue
            step = step_elem.text
            octave = octave_elem.text
            
            # Check for accidentals
            alter_elem = pitch.find('alter')
            alter = 0
            if alter_elem is not None and alter_elem.text:
                try:
                    alter = int(float(alter_elem.text)) # Some files might have float (e.g. 1.0)
                except ValueError:
                    logging.warning(f"Invalid alter value '{alter_elem.text}' for note {step}{octave}. Defaulting to no alteration.")
            
            # Determine the note name
            accidental = ""
            if alter == 1: accidental = "#"
            elif alter == 2: accidental = "##" # Double sharp
            elif alter == -1: accidental = "b"
            elif alter == -2: accidental = "bb" # Double flat
            
            note_name = f"{step}{accidental}{octave}"
            
            # Get duration
            duration_element = note_element.find('duration')
            if duration_element is None or not duration_element.text:
                logging.warning(f"Missing duration for note {note_name} in measure {measure_idx+1}, note {note_idx+1}. Skipping note.")
                continue
            try:
                duration_ticks = float(duration_element.text)
            except ValueError:
                logging.warning(f"Invalid duration value '{duration_element.text}' for note {note_name}. Skipping note.")
                continue

            duration_in_seconds = duration_ticks * seconds_per_division
            
            # Get lyrics/text if available
            lyric_text = None
            lyric_elem = note_element.find('.//lyric/text')
            if lyric_elem is not None and lyric_elem.text:
                lyric_text = lyric_elem.text.strip()

            notes.append({
                "note": note_name,
                "start_time": current_time,
                "duration": duration_in_seconds,
                "pitch": (step, int(octave), alter), # Store structured pitch
                "voice": int(note_element.find('voice').text) if note_element.find('voice') is not None and note_element.find('voice').text else 1,
                "text": lyric_text # Store lyric
            })
            
            current_time += duration_in_seconds
    
    logging.info(f"Successfully parsed {len(notes)} notes from {file_path}.")
    return notes

def create_fingerboard_frame(notes, current_time, frame_size=(1280, 720)):
    """Create a single frame of the fingerboard with the current note highlighted."""
    # Create a blank canvas
    img = Image.new('RGB', frame_size, color=(0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Calculate the position of the fingerboard in the frame
    fb_x = (frame_size[0] - FB_WIDTH) // 2
    fb_y = (frame_size[1] - FB_HEIGHT) // 2
    
    # Draw the fingerboard
    draw.rectangle([fb_x, fb_y, fb_x + FB_WIDTH, fb_y + FB_HEIGHT], fill=(50, 50, 50), outline=(100, 100, 100))
    
    # Draw the strings
    for i, string_name_label in enumerate(VIOLIN_STRINGS): # Renamed 'string' to 'string_name_label'
        y = fb_y + (i + 1) * STRING_SPACING
        draw.line([(fb_x, y), (fb_x + FB_WIDTH, y)], fill=STRING_COLORS[i], width=3)
        # Label the strings
        draw.text((fb_x - 30, y - 10), string_name_label, fill=(255, 255, 255))
    
    # Draw fret markers and label the positions
    # Label position 0
    draw.text((fb_x - 5, fb_y - 20), "0", fill=(150, 150, 150))
    # Label the rest of the positions
    for i in range(1, 16): # Fret positions
        x_pos = fb_x + i * FRET_SPACING
        draw.line([(x_pos, fb_y), (x_pos, fb_y + FB_HEIGHT)], fill=(100, 100, 100), width=1)
        # Label the positions: 0, -1, 1, 2, 2+, 3, ..., 13
        if i == 1: label = "-1"
        elif i == 2: label = "1"
        elif i == 3: label = "2"
        elif i == 4: label = "2+"
        else: label = str(i - 2) # i >= 5
        draw.text((x_pos - 5, fb_y - 20), label, fill=(150, 150, 150)) # Adjust x-position for better alignment
    
    active_notes_this_frame = []
    for note_info in notes: # Renamed 'note' to 'note_info' to avoid conflict
        if note_info["start_time"] <= current_time < note_info["start_time"] + note_info["duration"]:
            active_notes_this_frame.append(note_info)

    # Draw all notes (active or inactive state based on current_time)
    # This simplifies logic: draw all notes, then overwrite active ones with highlight
    for note_info in notes:
        note_name = note_info["note"]
        
        # Attempt to get position from NOTE_POSITIONS
        note_pos_data = NOTE_POSITIONS.get(note_name)
        
        # Handle alternative names if not found (e.g. Cb -> B, E# -> F)
        if not note_pos_data:
            # This is a simplified lookup, might need more robust handling for all enharmonics
            simplified_name = note_name.replace("##", "").replace("bb", "") # Basic double sharp/flat removal
            if "Cb" in simplified_name: simplified_name = simplified_name.replace("Cb", f"B{int(note_name[-1])-1}")
            elif "B#" in simplified_name: simplified_name = simplified_name.replace("B#", f"C{int(note_name[-1])+1}")
            elif "Fb" in simplified_name: simplified_name = simplified_name.replace("Fb", f"E{note_name[-1]}")
            elif "E#" in simplified_name: simplified_name = simplified_name.replace("E#", f"F{note_name[-1]}")
            note_pos_data = NOTE_POSITIONS.get(simplified_name)

        if note_pos_data:
            pos_x_fret, string_idx = note_pos_data
            x_coord = fb_x + pos_x_fret * FRET_SPACING
            y_coord = fb_y + (string_idx + 1) * STRING_SPACING
            
            is_active = note_info in active_notes_this_frame
            color = HIGHLIGHT_COLOR if is_active else NOTE_COLOR
            
            draw.ellipse((x_coord - 10, y_coord - 10, x_coord + 10, y_coord + 10), fill=color, outline=(255, 255, 255))

            if is_active:
                # Determine the finger position label based on pos_x_fret
                if pos_x_fret == 0: fret_label = "0"
                elif pos_x_fret == 1: fret_label = "-1"
                elif pos_x_fret == 2: fret_label = "1"
                elif pos_x_fret == 3: fret_label = "2"
                elif pos_x_fret == 4: fret_label = "2+"
                else: fret_label = str(pos_x_fret - 2) # pos_x_fret >= 5

                # Display note name or custom text above the note
                display_text = note_info.get("text") or f"{note_info['pitch'][0]}{fret_label}" # Use lyric if available
                try:
                    # Attempt to load a specific font, fall back to default
                    font_path = "arial.ttf" # Or some other common font file
                    if not os.path.exists(font_path) and os.environ.get("LAMBDA_TASK_ROOT"):
                        font_path = os.path.join(os.environ["LAMBDA_TASK_ROOT"], "arial.ttf") # For Lambda if packaged
                    
                    try:
                        label_font = ImageFont.truetype(font_path, 16)
                    except IOError:
                        label_font = ImageFont.load_default() # Fallback
                except Exception: # Catch-all for font loading issues
                    label_font = ImageFont.load_default()

                draw.text((x_coord - 10, y_coord - 30), display_text, fill=(255, 255, 255), font=label_font)
        else:
            logging.debug(f"Position not found for note: {note_name} at time {current_time:.2f}s")


    # Add title text (current time and active notes)
    try:
        # Attempt to load a specific font, fall back to default
        font_path = "arial.ttf" 
        if not os.path.exists(font_path) and os.environ.get("LAMBDA_TASK_ROOT"):
             font_path = os.path.join(os.environ["LAMBDA_TASK_ROOT"], "arial.ttf")

        try:
            title_font = ImageFont.truetype(font_path, 24)
        except IOError:
            logging.warning(f"Arial font not found at {font_path}, using default font. Text rendering might be basic.")
            title_font = ImageFont.load_default()
    except Exception as e:
        logging.error(f"Error loading font: {e}. Using default font.")
        title_font = ImageFont.load_default()

    active_note_display_names = [note_info.get("text") or note_info["note"] for note_info in active_notes_this_frame]
    title = f"Time: {current_time:.2f}s"
    if active_note_display_names:
        title += f" - Playing: {', '.join(active_note_display_names)}"
    
    # Calculate text size and position for centering
    text_width, text_height = draw.textsize(title, font=title_font)
    title_x = (frame_size[0] - text_width) / 2
    title_y = 30
    draw.text((title_x, title_y), title, fill=(255, 255, 255), font=title_font)
    
    return np.array(img, dtype=np.uint8)

def make_video(notes, output_file="violin_tutorial.mp4", fps=30, duration=None):
    """Create a video tutorial of the notes to be played on the violin."""
    logging.info(f"Starting video generation. Output: {output_file}, FPS: {fps}")
    if not notes:
        logging.warning("No notes provided to make_video. Generating empty video.")
        # Create a short, blank clip if no notes
        blank_clip = VideoClip(lambda t: np.zeros((720,1280,3), dtype=np.uint8), duration=1)
        blank_clip.write_videofile(output_file, codec="libx264", fps=fps, logger=None) # MoviePy can be verbose
        logging.info("Generated a short blank video as no notes were provided.")
        return output_file

    if duration is None:
        if notes:
            last_note = notes[-1]
            calculated_duration = last_note["start_time"] + last_note["duration"] + 1  # Add 1 second buffer
        else: # Should not happen if check above is done, but defensive
            calculated_duration = 1 
        logging.info(f"Video duration calculated: {calculated_duration:.2f}s")
    else:
        calculated_duration = duration
        logging.info(f"Video duration provided: {calculated_duration:.2f}s")
    
    try:
        clip = VideoClip(lambda t: create_fingerboard_frame(notes, t), duration=calculated_duration)
        # Set the frame rate using with_fps or directly in write_videofile
        # clip = clip.with_fps(fps) # This method doesn't exist. FPS is set in write_videofile.
        
        logging.info(f"Writing video file: {output_file} with FPS={fps}")
        # MoviePy's write_videofile can be quite verbose. Setting logger=None can reduce CloudWatch clutter.
        # For debugging, set logger='bar' or None for full logs.
        clip.write_videofile(output_file, codec="libx264", fps=fps, logger=None) 
        logging.info(f"Video generation successful: {output_file}")
    except Exception as e:
        logging.error(f"Error during video creation with MoviePy: {e}", exc_info=True)
        raise # Re-raise the exception to be caught by the caller
    
    return output_file

def main():
    """Main function to run the application."""
    # This main function is for command-line usage, not directly by Lambda.
    import argparse
    
    # Setup basic logging for CLI usage
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    parser = argparse.ArgumentParser(description="Generate a Synthesia-like video for violin from a MusicXML file.")
    parser.add_argument("input_file", help="Input MusicXML file")
    parser.add_argument("--output", "-o", default="violin_tutorial.mp4", help="Output video file (default: violin_tutorial.mp4)")
    parser.add_argument("--fps", type=int, default=30, help="Frames per second (default: 30)")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input_file):
        logging.error(f"Error: Input file '{args.input_file}' not found.")
        return
    
    logging.info(f"Processing CLI request for input: {args.input_file}")
    try:
        notes = parse_musicxml(args.input_file)
        
        if not notes:
            logging.info("No notes found in the input file.")
            return
        
        logging.info(f"Found {len(notes)} notes. Generating video to {args.output} at {args.fps} FPS...")
        output_video_file = make_video(notes, output_file=args.output, fps=args.fps)
        logging.info(f"Video generated successfully: {output_video_file}")

    except FileNotFoundError:
        logging.error(f"File not found: {args.input_file}")
    except ValueError as ve: # Catch specific errors from parsing
        logging.error(f"Error processing MusicXML: {ve}")
    except ET.ParseError as pe:
        logging.error(f"Invalid XML structure in {args.input_file}: {pe}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}", exc_info=True)

if __name__ == "__main__":
    main()