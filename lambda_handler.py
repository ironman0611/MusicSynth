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
    # Configure logging for local testing
    # Ensure messages are visible during local execution
    if not logging.getLogger().hasHandlers(): # Avoid adding multiple handlers if script is re-run in some envs
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(funcName)s - %(message)s')
    
    logging.info("--- Starting Enhanced Local Testing for lambda_handler.py ---")
    
    # --- Test Helper Function ---
    def run_test(test_name, event, expected_status_code, expected_body_contains=None, check_video_content=False):
        logging.info(f"\n--- Test: {test_name} ---")
        logging.info(f"Event: {json.dumps(event, indent=1)}")
        
        result = handler(event, None)
        logging.info(f"Raw Result: {json.dumps(result, indent=1)}")

        status_ok = result.get("statusCode") == expected_status_code
        body_ok = True
        video_content_ok = True

        if isinstance(result.get("body"), str):
            try:
                body_json = json.loads(result["body"])
            except json.JSONDecodeError:
                body_json = {"error": "Response body is not valid JSON"} # Handle non-JSON body
                if expected_body_contains: # If we expected parsable JSON, this is a fail
                    body_ok = False

            if expected_body_contains:
                # Check if all expected strings are in the body (either as key or value)
                body_ok = all(keyword in str(body_json) for keyword in expected_body_contains)
            
            if check_video_content:
                video_content_ok = "video_content" in body_json and \
                                   isinstance(body_json["video_content"], str) and \
                                   len(body_json["video_content"]) > 0 and \
                                   "filename" in body_json and \
                                   isinstance(body_json["filename"], str)
                if not video_content_ok:
                    logging.error(f"Video content check failed. Body: {body_json}")

        else: # Body is not a string, which is unexpected for valid/error JSON responses
            body_ok = False if expected_body_contains else True # Fail if we expected content
            if expected_status_code == 200 : # Should always have string body for 200
                 body_ok = False


        if status_ok and body_ok and video_content_ok:
            logging.info(f"PASS: {test_name}. Status: {result.get('statusCode')}")
            return True
        else:
            logging.error(f"FAIL: {test_name}. Expected Status: {expected_status_code}, Got: {result.get('statusCode')}")
            if not body_ok:
                 logging.error(f"  Body check failed. Expected to contain: {expected_body_contains}, Got body: {result.get('body')}")
            if not video_content_ok and check_video_content:
                 logging.error(f"  Video content validation failed.")
            return False

    # --- Test Data ---
    simple_musicxml_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="3.1">
  <part-list><score-part id="P1"><part-name>Music</part-name></score-part></part-list>
  <part id="P1"><measure number="1">
      <attributes><divisions>1</divisions><key><fifths>0</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>whole</type></note>
  </measure></part>
</score-partwise>"""
    valid_b64_musicxml = base64.b64encode(simple_musicxml_content.encode('utf-8')).decode('utf-8')
    
    # Dummy image content (e.g., a 1x1 PNG) base64 encoded
    # (from: `echo -n "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=" | base64 -d > 1x1.png`)
    # No, this is already base64. The original bytes for a 1x1 png are very small.
    # Minimal PNG:
    # Hex: 89 50 4E 47 0D 0A 1A 0A 00 00 00 0D 49 48 44 52 00 00 00 01 00 00 00 01 08 06 00 00 00 1F 15 C4 89 00 00 00 00 49 45 4E 44 AE 42 60 82
    # Let's use a simpler text file for image test, as content doesn't matter for this test.
    dummy_image_content_b64 = base64.b64encode(b"This is a dummy image content.").decode('utf-8')

    tests_passed = 0
    total_tests = 0

    # --- Scenario 1: Valid MusicXML File Event ---
    total_tests += 1
    event1 = {
        "body": json.dumps({
            "filename": "test_song.musicxml",
            "file_content": valid_b64_musicxml
        })
    }
    if run_test("Valid MusicXML", event1, 200, check_video_content=True):
        tests_passed += 1

    # --- Scenario 2: Event with Missing `file_content` ---
    total_tests += 1
    event2 = {
        "body": json.dumps({
            "filename": "missing_content.xml"
            # "file_content": "is missing"
        })
    }
    if run_test("Missing file_content", event2, 400, expected_body_contains=["Missing file_content or filename"]):
        tests_passed += 1

    # --- Scenario 3: Event with Missing `filename` ---
    total_tests += 1
    event3 = {
        "body": json.dumps({
            # "filename": "is missing",
            "file_content": valid_b64_musicxml
        })
    }
    if run_test("Missing filename", event3, 400, expected_body_contains=["Missing file_content or filename"]):
        tests_passed += 1
        
    # --- Scenario 4: Event with Malformed JSON Body ---
    total_tests += 1
    event4 = {
        "body": "This is not a valid JSON string { filename: 'test.xml', file_content: '...' "
    }
    if run_test("Malformed JSON Body", event4, 400, expected_body_contains=["Malformed JSON"]):
        tests_passed += 1

    # --- Scenario 5: Event with Non-Base64 `file_content` ---
    total_tests += 1
    event5 = {
        "body": json.dumps({
            "filename": "invalid_base64.xml",
            "file_content": "This is definitely not valid base64!@#$%^"
        })
    }
    if run_test("Non-Base64 file_content", event5, 400, expected_body_contains=["Invalid base64 encoded file_content"]):
        tests_passed += 1

    # --- Scenario 6: Test with Image File (Simulating `oemer` disabled) ---
    # FileProcessor is expected to return success=False and a message for image files
    # when OMR/oemer is not available (which is the case in Lambda by default).
    total_tests += 1
    event6 = {
        "body": json.dumps({
            "filename": "test_image.png",
            "file_content": dummy_image_content_b64 # Dummy base64 content
        })
    }
    # The handler should return 500 because FileProcessor returns (False, message, None, None)
    # and the handler tries to use the None paths.
    # The message from FileProcessor should be in "details".
    if run_test("Image File (OMR Disabled)", event6, 500, 
                expected_body_contains=["File processing failed", "Image processing is not available"]):
        tests_passed += 1
        
    # --- Scenario 7: Body is a Python dict directly (simulating certain API Gateway configurations or direct invokes) ---
    total_tests +=1
    event7 = {
        "body": { # Not a JSON string, but a dict
            "filename": "dict_body_test.musicxml",
            "file_content": valid_b64_musicxml
        }
    }
    if run_test("Body as Python Dict", event7, 200, check_video_content=True):
        tests_passed +=1

    # --- Scenario 8: Empty JSON string in body ---
    total_tests +=1
    event8 = {"body": "{}"}
    if run_test("Empty JSON string in body", event8, 400, expected_body_contains=["Missing file_content or filename"]):
        tests_passed +=1
        
    # --- Scenario 9: No body key in event ---
    total_tests +=1
    event9 = {} # No "body" key at all
    if run_test("No body key in event", event9, 400, expected_body_contains=["Request body must be a valid JSON object or JSON string"]): # Adjusted based on new check
        tests_passed +=1

    # --- Summary ---
    logging.info(f"\n--- Local Testing Summary ---")
    logging.info(f"Total tests run: {total_tests}")
    logging.info(f"Tests passed: {tests_passed}")
    logging.info(f"Tests failed: {total_tests - tests_passed}")
    if total_tests == tests_passed:
        logging.info("All tests passed successfully!")
    else:
        logging.warning("Some tests failed.")
    logging.info("--- End of Local Testing ---")
