import os
import tempfile
import subprocess
import time
from datetime import datetime
import logging # Added
# import streamlit as st # Removed Streamlit dependency
from synthesia import parse_musicxml, make_video
import shutil
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class FileProcessor:
    def __init__(self, base_temp_dir=None): # Modified constructor
        self.timing_stats = {}
        self.project_dir = os.path.dirname(os.path.abspath(__file__))

        if base_temp_dir:
            # Running in Lambda or similar environment, use the provided base directory
            self.base_dir = base_temp_dir
            self.temp_dir = os.path.join(self.base_dir, 'temp_files')
            self.xml_dir = os.path.join(self.base_dir, 'xml_out_files')
        else:
            # Default behavior (e.g., local Streamlit app)
            self.base_dir = self.project_dir
            self.temp_dir = os.path.join(self.base_dir, 'temp')
            self.xml_dir = os.path.join(self.base_dir, 'xml_files')

        # Create necessary directories
        for directory in [self.temp_dir, self.xml_dir]:
            if not os.path.exists(directory):
                # Lambda has write access to /tmp, mode 0o777 should be fine.
                os.makedirs(directory, mode=0o777, exist_ok=True)
                logging.info(f"Created directory: {directory}")
            else:
                # Ensure existing directories have proper permissions if not in Lambda /tmp
                if not base_temp_dir: # Only chmod if not using a predefined base_temp_dir like /tmp
                    try:
                        os.chmod(directory, 0o777)
                    except Exception as e:
                        logging.warning(f"Could not chmod {directory}: {e}. This might be fine in some environments.")
        
        # Oemer configuration
        if os.environ.get('AWS_LAMBDA_FUNCTION_NAME'):
            logging.info("Running in AWS Lambda environment. OMR (image processing) will be disabled.")
            self.use_cloud_omr = True # Disable Oemer by default in Lambda
            self.oemer_path = None
        elif os.environ.get('STREAMLIT_SERVER_ENVIRONMENT') == 'cloud':
            logging.info("Running in Streamlit Cloud. OMR (image processing) will be disabled.")
            self.use_cloud_omr = True
            self.oemer_path = None
        else:
            # Local environment, try to find Oemer
            try:
                result = subprocess.run(["which", "oemer"], capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    logging.warning("Oemer executable not found in PATH. Image processing will be disabled.")
                    self.use_cloud_omr = True
                    self.oemer_path = None
                else:
                    self.oemer_path = result.stdout.strip()
                    self.use_cloud_omr = False
                    logging.info(f"Oemer path: {self.oemer_path}")
            except Exception as e:
                logging.error(f"Error setting up Oemer: {str(e)}. Image processing will be disabled.")
                self.use_cloud_omr = True
                self.oemer_path = None
    
    def process_uploaded_file(self, uploaded_file):
        """
        Process an uploaded MusicXML or image file and generate a video visualization.
        
        Args:
            uploaded_file: The uploaded file object from Streamlit
            
        Returns:
            tuple: (success, message, output_path)
        """
        if uploaded_file is None:
            logging.error("No file uploaded.")
            return False, "No file uploaded", None, None # Added None for output_filename
        
        original_filename = uploaded_file.name
        filename_lower = original_filename.lower()
        is_musicxml = filename_lower.endswith('.musicxml') or filename_lower.endswith('.xml')
        is_image = filename_lower.endswith('.png') or filename_lower.endswith('.jpg') or filename_lower.endswith('.jpeg')
        
        if not (is_musicxml or is_image):
            logging.error(f"Unsupported file type: {original_filename}")
            return False, "Please upload a MusicXML file (.musicxml, .xml) or an image file (.png, .jpg, .jpeg)", None, None
        
        # Use self.temp_dir which is now correctly set by __init__ (could be session-specific)
        # The lambda_handler will manage the creation/deletion of the overall session_dir (base_temp_dir)
        # FileProcessor just uses subdirectories within it.
        
        # We expect uploaded_file.getbuffer() to provide the content bytes.
        # The lambda_handler will save the file initially.
        # For FileProcessor, temp_file_path is where it *expects* the file to be.
        # Or, it can directly use the bytes from uploaded_file.getbuffer()
        
        # Let's assume the file is already saved at a path by the caller (lambda_handler)
        # and that path is `uploaded_file.filepath_on_lambda_tmp` or similar.
        # For now, let's resave it into FileProcessor's own temp_dir structure.
        # This might be redundant if lambda_handler already saved it to a good spot.
        # However, process_uploaded_file is also used by the Streamlit app.

        # Create a unique ID for this processing instance if not part of a larger session_id from constructor
        processing_id = str(uuid.uuid4())
        # The actual working directory for this specific file processing run
        current_processing_temp_dir = os.path.join(self.temp_dir, f"processing_{processing_id}")
        os.makedirs(current_processing_temp_dir, mode=0o777, exist_ok=True)
        logging.info(f"Created processing-specific temp directory: {current_processing_temp_dir}")

        save_start = time.time()
        # temp_file_path is where this function will save the file for its own processing
        temp_file_path = os.path.join(current_processing_temp_dir, original_filename)
        logging.info(f"Saving uploaded file content to: {temp_file_path}")
        try:
            with open(temp_file_path, 'wb') as f:
                f.write(uploaded_file.getbuffer())
            os.chmod(temp_file_path, 0o666) # Permissions for the file itself
        except Exception as e:
            logging.error(f"Failed to save uploaded file to {temp_file_path}: {e}")
            return False, f"Failed to save uploaded file: {e}", None, None

        self.timing_stats['file_save'] = time.time() - save_start
            
        musicxml_path = None # Initialize musicxml_path

        try:
            if is_image:
                if self.use_cloud_omr or not self.oemer_path:
                    msg = "Image processing is not available in this environment. Please upload a MusicXML file."
                    logging.warning(msg)
                    return False, msg, None, None
                else:
                    # Use Oemer for local processing
                    logging.info(f"Running Oemer on image: {temp_file_path}")
                    # Oemer output goes into current_processing_temp_dir
                    cmd = [self.oemer_path, "-o", current_processing_temp_dir, "--save-cache", "-d", temp_file_path]
                    oemer_start = time.time()
                    # Changed from subprocess.run to handle potential hangs or long processes
                    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    stdout, stderr = process.communicate(timeout=120) # 2 min timeout for Oemer
                    
                    if process.returncode != 0:
                        logging.error(f"Oemer failed. Return code: {process.returncode}, Stderr: {stderr.decode('utf-8', 'ignore')}")
                        return False, f"Oemer failed: {stderr.decode('utf-8', 'ignore')}", None, None
                    self.timing_stats['oemer_processing'] = time.time() - oemer_start
                    
                    basename = os.path.splitext(os.path.basename(temp_file_path))[0]
                    # Oemer might create <basename>.musicxml or <basename>.xml
                    possible_musicxml_paths = [
                        os.path.join(current_processing_temp_dir, f"{basename}.musicxml"),
                        os.path.join(current_processing_temp_dir, f"{basename}.xml")
                    ]
                    
                    for p_path in possible_musicxml_paths:
                        if os.path.exists(p_path):
                            musicxml_path = p_path
                            break
                    
                    if not musicxml_path:
                        logging.error(f"Oemer did not produce a MusicXML file for {basename} in {current_processing_temp_dir}")
                        return False, f"Oemer did not produce a MusicXML file for {basename}", None, None
                    
                    logging.info(f"Oemer produced MusicXML file: {musicxml_path}")
            else: # It's a MusicXML file
                musicxml_path = temp_file_path
                logging.info(f"Using uploaded MusicXML file: {musicxml_path}")

            # Save a copy of the (potentially Oemer-generated) MusicXML file to self.xml_dir for records
            if musicxml_path and os.path.exists(musicxml_path):
                xml_record_filename = f"{os.path.splitext(os.path.basename(original_filename))[0]}_{processing_id}.musicxml"
                xml_save_path = os.path.join(self.xml_dir, xml_record_filename)
                try:
                    shutil.copy2(musicxml_path, xml_save_path)
                    os.chmod(xml_save_path, 0o666)
                    logging.info(f"Saved copy of MusicXML to: {xml_save_path}")
                except Exception as e:
                    logging.warning(f"Could not save copy of MusicXML to {xml_save_path}: {e}")
            
            logging.info(f"Parsing MusicXML file: {musicxml_path}")
            parse_start = time.time()
            notes = parse_musicxml(musicxml_path) # This can raise exceptions
            self.timing_stats['musicxml_parsing'] = time.time() - parse_start
            
            output_video_basename = os.path.splitext(os.path.basename(musicxml_path))[0] + '_visualization.mp4'
            # Output video to current_processing_temp_dir
            output_video_path = os.path.join(current_processing_temp_dir, output_video_basename)
            
            logging.info(f"Generating video: {output_video_path}")
            video_start = time.time()
            make_video(notes, output_file=output_video_path) # This can raise exceptions
            os.chmod(output_video_path, 0o666)
            self.timing_stats['video_generation'] = time.time() - video_start
            
            self._log_timing_stats(original_filename, current_processing_temp_dir) # Log stats to the processing-specific dir
            
            logging.info(f"Video generated successfully: {output_video_path}")
            return True, "Video generated successfully", output_video_path, output_video_basename # Return output_filename too
            
        except subprocess.TimeoutExpired:
            logging.error("Oemer processing timed out.")
            return False, "OMR processing timed out. The music sheet might be too complex or large.", None, None
        except Exception as e:
            logging.error(f"Error processing file {original_filename}: {str(e)}", exc_info=True) # Log traceback
            return False, f"Error processing file: {str(e)}", None, None
        # No finally block for cleaning current_processing_temp_dir here,
        # The lambda_handler will clean the entire base_temp_dir or FileProcessor.cleanup() for Streamlit.

    def cleanup(self):
        """Clean up temporary files from self.temp_dir (used by Streamlit app)"""
        # This cleanup is more for the Streamlit app.
        # For Lambda, the entire /tmp/session_<id> dir is removed by lambda_handler.
        # This method is primarily for non-Lambda use where temp_dir is persistent.
        # For Lambda, the base_temp_dir passed to __init__ is ephemeral.
        if not os.environ.get('AWS_LAMBDA_FUNCTION_NAME'): # Only run this if not in Lambda
            logging.info(f"Cleaning up general temp directory: {self.temp_dir}")
            cleaned_count = 0
            try:
                for item in os.listdir(self.temp_dir):
                    item_path = os.path.join(self.temp_dir, item)
                    # Expecting subdirectories like 'processing_<uuid>'
                    if os.path.isdir(item_path) and item.startswith('processing_'):
                        try:
                            shutil.rmtree(item_path)
                            logging.info(f"Removed temp processing directory: {item_path}")
                            cleaned_count +=1
                        except Exception as e_inner:
                            logging.error(f"Error removing directory {item_path}: {e_inner}")
                if cleaned_count > 0:
                     # Recreate the base temp directory with proper permissions if it was fully cleared
                    os.makedirs(self.temp_dir, mode=0o777, exist_ok=True)
                logging.info(f"Cleanup of {self.temp_dir} complete. Removed {cleaned_count} processing directories.")
            except Exception as e:
                logging.error(f"Error during cleanup of {self.temp_dir}: {str(e)}")
        else:
            logging.info("Skipping FileProcessor.cleanup() in Lambda environment as /tmp is ephemeral.")

    def _log_timing_stats(self, filename, processing_dir_path): # Changed session_dir to processing_dir_path
        """Log timing statistics to a file in the specified processing directory."""
        log_entry = f"\n--- {datetime.now()} ---\n"
        log_entry += f"File: {filename}\n"
        for step, duration in self.timing_stats.items():
            log_entry += f" - {step}: {duration:.2f} seconds\n"
        log_entry += "-" * 50 + "\n"
        
        log_path = os.path.join(processing_dir_path, 'processing_stats.log')
        try:
            with open(log_path, 'a') as f:
                f.write(log_entry)
            os.chmod(log_path, 0o666)
            logging.info(f"Timing stats logged to: {log_path}")
        except Exception as e:
            logging.error(f"Failed to write timing stats to {log_path}: {e}")