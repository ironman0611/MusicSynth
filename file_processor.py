import os
import tempfile
import subprocess
import time
from datetime import datetime
from synthesia import parse_musicxml, make_video

class FileProcessor:
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp()
        self.timing_stats = {}
        # Find the full path to the oemer executable
        result = subprocess.run(["which", "oemer"], capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError("Oemer executable not found. Please ensure it is installed and in your PATH.")
        self.oemer_path = result.stdout.strip()
        print(f"Oemer path: {self.oemer_path}")
    
    def process_uploaded_file(self, uploaded_file):
        """
        Process an uploaded MusicXML or image file and generate a video visualization.
        
        Args:
            uploaded_file: The uploaded file object from Streamlit
            
        Returns:
            tuple: (success, message, output_path)
        """
        if uploaded_file is None:
            return False, "No file uploaded", None
        
        filename = uploaded_file.name.lower()
        is_musicxml = filename.endswith('.musicxml') or filename.endswith('.xml')
        is_image = filename.endswith('.png') or filename.endswith('.jpg') or filename.endswith('.jpeg')
        
        if not (is_musicxml or is_image):
            return False, "Please upload a MusicXML file (.musicxml, .xml) or an image file (.png, .jpg, .jpeg)", None
        
        try:
            # Save the uploaded file to a temporary location
            save_start = time.time()
            temp_file_path = os.path.join(self.temp_dir, uploaded_file.name)
            print(f"Saving uploaded file to: {temp_file_path}")
            with open(temp_file_path, 'wb') as f:
                f.write(uploaded_file.getbuffer())
            self.timing_stats['file_save'] = time.time() - save_start
            
            # If image, run Oemer to get MusicXML
            if is_image:
                print(f"Running Oemer on image: {temp_file_path}")
                # Call oemer CLI using the full path with correct flags
                cmd = [self.oemer_path, "-o", self.temp_dir, "--save-cache", "-d", temp_file_path]
                oemer_start = time.time()
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    print(f"Oemer failed with error: {result.stderr}")
                    return False, f"Oemer failed: {result.stderr}", None
                self.timing_stats['oemer_processing'] = time.time() - oemer_start
                # Find the output MusicXML file
                basename = os.path.splitext(os.path.basename(temp_file_path))[0]
                musicxml_path = os.path.join(self.temp_dir, f"{basename}.musicxml")
                if not os.path.exists(musicxml_path):
                    # Sometimes oemer may output .xml instead
                    musicxml_path = os.path.join(self.temp_dir, f"{basename}.xml")
                    if not os.path.exists(musicxml_path):
                        print(f"Oemer did not produce a MusicXML file for {basename}")
                        return False, f"Oemer did not produce a MusicXML file for {basename}", None
                print(f"Oemer produced MusicXML file: {musicxml_path}")
            else:
                # Use the uploaded MusicXML file
                musicxml_path = temp_file_path
                print(f"Using uploaded MusicXML file: {musicxml_path}")
            
            # Parse the MusicXML file
            print(f"Parsing MusicXML file: {musicxml_path}")
            notes = parse_musicxml(musicxml_path)
            
            # Generate output video path
            output_filename = os.path.splitext(os.path.basename(musicxml_path))[0] + '_visualization.mp4'
            output_path = os.path.join(self.temp_dir, output_filename)
            
            # Create the video
            print(f"Generating video: {output_path}")
            video_start = time.time()
            make_video(notes, output_file=output_path)
            self.timing_stats['video_generation'] = time.time() - video_start
            
            # Log timing statistics
            self._log_timing_stats(uploaded_file.name)
            
            return True, "Video generated successfully", output_path
            
        except Exception as e:
            print(f"Error processing file: {str(e)}")
            return False, f"Error processing file: {str(e)}", None
        
    def cleanup(self):
        """Clean up temporary files"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def _log_timing_stats(self, filename):
        """Log timing statistics to a file."""
        log_entry = f"\n{datetime.now()}\n"
        log_entry += f"File: {filename}\n"
        for step, duration in self.timing_stats.items():
            log_entry += f"{step}: {duration:.2f} seconds\n"
        log_entry += "-" * 50
        
        with open('processing_stats.log', 'a') as f:
            f.write(log_entry) 