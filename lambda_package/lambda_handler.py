import json
import base64
import os
import uuid
import logging
import shutil # For cleanup
from file_processor import FileProcessor # Import actual FileProcessor

# Configure logging
# Logs will go to CloudWatch in AWS Lambda
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Adapter class for the uploaded file to match FileProcessor's expected interface
class LambdaUploadedFile:
    def __init__(self, name, content_bytes):
        self.name = name
        self._content_bytes = content_bytes
        logging.info(f"LambdaUploadedFile created for '{name}' ({len(content_bytes)} bytes)")

    def getbuffer(self):
        # FileProcessor expects getbuffer() to return a memoryview or bytes-like object
        return self._content_bytes

def handler(event, context):
    logging.info(f"Received event: {json.dumps(event, indent=2)}")

    session_id = str(uuid.uuid4())
    # Create a unique temporary directory within /tmp for this request
    base_temp_dir = os.path.join("/tmp", f"session_{session_id}")
    # This base_temp_dir will house subdirectories created by FileProcessor
    
    temp_file_path = None # Initialize for finally block

    try:
        os.makedirs(base_temp_dir, exist_ok=True)
        logging.info(f"Created base temporary directory: {base_temp_dir}")

        if isinstance(event.get("body"), str):
            try:
                body = json.loads(event["body"])
            except json.JSONDecodeError as e:
                logging.error(f"Malformed JSON in request body: {e}")
                return {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"error": "Malformed JSON in request body"})
                }
        else:
            # If body is already a dict (e.g. from Lambda test event UI), use it directly
            body = event.get("body", {}) 
            if not isinstance(body, dict): # Still ensure it's a dict
                 logging.error(f"Request body is not a JSON string or a valid JSON object. Type: {type(body)}")
                 return {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"error": "Request body must be a valid JSON object or JSON string."})
                }


        file_content_b64 = body.get("file_content")
        original_filename = body.get("filename")

        if not file_content_b64 or not original_filename:
            logging.error("Missing file_content or filename in the event body.")
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "Missing file_content or filename"})
            }

        # Decode the base64 file content
        try:
            decoded_file_content = base64.b64decode(file_content_b64)
        except base64.binascii.Error as e:
            logging.error(f"Error decoding base64 file content: {e}")
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "Invalid base64 encoded file_content"})
            }
        
        # Note: FileProcessor will save the file to its own sub-temp directory.
        # We don't strictly need to save it here first, but LambdaUploadedFile needs the bytes.
        # temp_file_path = os.path.join(base_temp_dir, original_filename) # Not strictly needed to save here
        # with open(temp_file_path, "wb") as f:
        #     f.write(decoded_file_content)
        # logging.info(f"Decoded file content prepared for processing (not saved directly by handler).")

        # Instantiate FileProcessor, passing the base_temp_dir for it to manage its subdirs
        file_processor = FileProcessor(base_temp_dir=base_temp_dir)
        logging.info(f"FileProcessor instantiated with base_temp_dir: {base_temp_dir}")

        # Create LambdaUploadedFile object
        uploaded_file_obj = LambdaUploadedFile(name=original_filename, content_bytes=decoded_file_content)
        logging.info(f"LambdaUploadedFile object created for: {original_filename}")

        # Call process_uploaded_file
        # It now returns: success, message, output_path, output_filename
        success, message, processed_output_path, processed_output_filename = file_processor.process_uploaded_file(uploaded_file_obj)
        
        if not success:
            logging.error(f"File processing failed: {message}")
            return {
                "statusCode": 500, # Or 422 if it's a user file issue
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "File processing failed", "details": message})
            }

        logging.info(f"File processing successful. Output path: {processed_output_path}, Output filename: {processed_output_filename}")

        # Read the generated video file
        with open(processed_output_path, "rb") as f:
            video_content_bytes = f.read()

        # Base64 encode the video file content
        encoded_video = base64.b64encode(video_content_bytes).decode('utf-8')
        logging.info(f"Video content encoded to base64 (length: {len(encoded_video)}).")

        # Return success response
        response = {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*", # Add CORS header if API Gateway is direct
            },
            "body": json.dumps({"video_content": encoded_video, "filename": processed_output_filename})
        }
        logging.info(f"Returning success response.")
        return response

    except Exception as e:
        logging.error(f"Error during processing: {str(e)}", exc_info=True) # Log full traceback
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Internal server error", "details": str(e)})
        }
    finally:
        # Clean up the entire base_temp_dir for this session
        if os.path.exists(base_temp_dir):
            try:
                shutil.rmtree(base_temp_dir)
                logging.info(f"Successfully removed base temporary directory and all its contents: {base_temp_dir}")
            except Exception as e_cleanup:
                logging.error(f"Error during cleanup of {base_temp_dir}: {str(e_cleanup)}", exc_info=True)

if __name__ == '__main__':
    # --- Local Testing Setup ---
    # Create dummy /tmp if it doesn't exist (for local testing outside Lambda)
    if not os.path.exists("/tmp"):
        os.makedirs("/tmp", exist_ok=True)
    
    # Create a dummy synthesia.py if it's not present (for local FileProcessor testing)
    if not os.path.exists("synthesia.py"):
        with open("synthesia.py", "w") as f:
            f.write("""
import logging
from PIL import Image, ImageDraw, ImageFont
def parse_musicxml(file_path):
    logging.info(f"Mock parsing MusicXML: {file_path}")
    # Return a list of mock notes with start_time, duration, pitch, and voice
    return [{'start_time': 0, 'duration': 1, 'pitch': ('C', 4), 'voice': 1, 'text': None},
            {'start_time': 1, 'duration': 1, 'pitch': ('E', 4), 'voice': 1, 'text': 'Hello'},
            {'start_time': 2, 'duration': 1, 'pitch': ('G', 4), 'voice': 1, 'text': None}]

def make_video(notes, output_file="output.mp4", width=1280, height=720, fps=24):
    logging.info(f"Mock creating video for {len(notes)} notes, output to {output_file}")
    # Create a dummy mp4 file for testing
    try:
        with open(output_file, "wb") as vid_file:
            vid_file.write(b"mock mp4 content")
        logging.info(f"Mock video file created: {output_file}")
    except Exception as e:
        logging.error(f"Failed to create mock video file: {e}")
        raise
    return True
""")
    logging.info("--- Local testing __main__ block of lambda_handler.py ---")
    
    # Example event for local testing: Valid MusicXML
    # A very simple MusicXML content
    simple_musicxml_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="3.1">
  <part-list>
    <score-part id="P1">
      <part-name>Music</part-name>
    </score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <key><fifths>0</fifths></key>
        <time><beats>4</beats><beat-type>4</beat-type></time>
        <clef><sign>G</sign><line>2</line></clef>
      </attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>whole</type></note>
    </measure>
  </part>
</score-partwise>
"""
    example_event_musicxml = {
        "body": json.dumps({
            "filename": "simple.musicxml",
            "file_content": base64.b64encode(simple_musicxml_content.encode('utf-8')).decode('utf-8')
        })
    }
    logging.info("\n--- Testing Lambda Handler Locally (Valid MusicXML) ---")
    result_musicxml = handler(example_event_musicxml, None)
    logging.info("\n--- Handler Result (Valid MusicXML) ---")
    # Only print filename and if video_content exists, not the full base64 string
    if result_musicxml and 'body' in result_musicxml:
        body_dict = json.loads(result_musicxml['body'])
        logging.info(f"Status Code: {result_musicxml.get('statusCode')}")
        logging.info(f"Filename in response: {body_dict.get('filename')}")
        logging.info(f"Video content present: {'video_content' in body_dict and bool(body_dict['video_content'])}")
    else:
        logging.info(json.dumps(result_musicxml, indent=2))


    # Test error case: missing filename
    example_event_error_missing_param = {
        "body": json.dumps({
            "file_content": base64.b64encode(b"test content").decode('utf-8')
        })
    }
    logging.info("\n--- Testing Error Case (Missing Filename) ---")
    result_error_missing_param = handler(example_event_error_missing_param, None)
    logging.info("\n--- Handler Error Result (Missing Filename) ---")
    logging.info(json.dumps(result_error_missing_param, indent=2))

    # Test error case: malformed body (not JSON string, but a Python dict directly)
    # This simulates how API Gateway might pass a parsed JSON if 'Use Lambda Proxy integration' is off,
    # or how a direct Lambda invoke might pass it.
    example_event_malformed_body_dict = {
        "body": { 
            "filename": "test_dict_body.xml",
            "file_content": base64.b64encode(simple_musicxml_content.encode('utf-8')).decode('utf-8')
        }
    }
    logging.info("\n--- Testing Case (Body as Dict directly) ---")
    result_malformed_dict = handler(example_event_malformed_body_dict, None)
    logging.info("\n--- Handler Result (Body as Dict directly) ---")
    if result_malformed_dict and 'body' in result_malformed_dict:
        body_dict_direct = json.loads(result_malformed_dict['body'])
        logging.info(f"Status Code: {result_malformed_dict.get('statusCode')}")
        logging.info(f"Filename in response: {body_dict_direct.get('filename')}")
        logging.info(f"Video content present: {'video_content' in body_dict_direct and bool(body_dict_direct['video_content'])}")


    # Test with an empty JSON string in body
    example_event_empty_body_json = {
        "body": "{}"
    }
    logging.info("\n--- Testing Error Case (Empty JSON Body) ---")
    result_empty_body_json = handler(example_event_empty_body_json, None)
    logging.info("\n--- Handler Empty JSON Body Result ---")
    logging.info(json.dumps(result_empty_body_json, indent=2))

    # Test with no body key
    example_event_no_body_key = {}
    logging.info("\n--- Testing Error Case (No Body Key) ---")
    result_no_body_key = handler(example_event_no_body_key, None)
    logging.info("\n--- Handler No Body Key Result ---")
    logging.info(json.dumps(result_no_body_key, indent=2))
    
    # Test with invalid base64 content
    example_event_invalid_base64 = {
        "body": json.dumps({
            "filename": "invalid_base64.xml",
            "file_content": "This is not valid base64"
        })
    }
    logging.info("\n--- Testing Error Case (Invalid Base64) ---")
    result_invalid_base64 = handler(example_event_invalid_base64, None)
    logging.info("\n--- Handler Invalid Base64 Result ---")
    logging.info(json.dumps(result_invalid_base64, indent=2))

    logging.info("\n--- Local testing finished ---")
