import streamlit as st
# from file_processor import FileProcessor # Removed local file processor
import os
import time
from datetime import datetime
import pandas as pd
import requests # Added for API calls
import base64   # Added for encoding/decoding
import io       # Added for byte streams

# --- API Configuration ---
# These should be configured securely, e.g., via Streamlit secrets or environment variables
API_GATEWAY_URL = "YOUR_API_GATEWAY_ENDPOINT_URL_HERE/processfile"  # Replace with actual URL later
API_KEY = "YOUR_API_KEY_HERE"  # Replace with actual API key later
# --- End API Configuration ---

# Set page config
st.set_page_config(
    page_title="MusicSynth",
    page_icon="🎵",
    layout="wide"
)

# # Initialize session state for file processor if it doesn't exist # Removed FileProcessor instantiation
# if 'file_processor' not in st.session_state:
#     st.session_state.file_processor = FileProcessor()

st.title("🎵 MusicSynth - Sheet Music Visualizer")

# Add environment info
# This check can remain for filtering uploader types, as image processing is disabled in the Lambda by default.
is_cloud = os.environ.get('STREAMLIT_SERVER_ENVIRONMENT') == 'cloud'
if is_cloud: # Or if API_GATEWAY_URL is not the placeholder
    st.info("Processing via API. Image processing (OMR) is disabled if using the default cloud Lambda. MusicXML files are preferred.")
else: # Potentially local dev without API or with local API
    st.info("Local or custom environment. Ensure your API endpoint supports the file types.")


# File upload section
st.header("Upload MusicXML or Image File")
# The Lambda function currently disables OMR, so restrict to MusicXML if calling the default Lambda.
# If a custom API endpoint supports images, this type list can be expanded.
uploader_types = ['musicxml', 'xml'] 
# Example: allow images if a specific (non-default) API URL is set
# if API_GATEWAY_URL != "YOUR_API_GATEWAY_ENDPOINT_URL_HERE/processfile":
#    uploader_types.extend(['png', 'jpg', 'jpeg'])

uploaded_file = st.file_uploader(
    "Choose a MusicXML file (.musicxml, .xml)" if API_GATEWAY_URL.startswith("YOUR_API_GATEWAY_ENDPOINT_URL_HERE") 
    else "Choose a MusicXML (.musicxml, .xml) or Image file (.png, .jpg, .jpeg) if your API supports it.",
    type=uploader_types 
)

if uploaded_file is not None:
    # Initialize timing statistics for API call
    timing_stats = {
        'start_time': time.time(),
        'steps': {} # Will store 'api_call_duration'
    }
    
    # Process the uploaded file via API
    with st.spinner("Processing your file via API... This may take a moment."):
        st.info(f"Starting API call for file: {uploaded_file.name}")
        
        api_call_start_time = time.time()
        success = False # Initialize success flag
        
        try:
            # Get file content
            file_bytes = uploaded_file.getbuffer().tobytes()
            # Base64 encode
            encoded_file_content = base64.b64encode(file_bytes).decode('utf-8')
            
            # Prepare payload for API
            payload = {
                "filename": uploaded_file.name,
                "file_content": encoded_file_content
            }
            
            # Prepare headers for API
            headers = {
                "x-api-key": API_KEY,
                "Content-Type": "application/json" # Ensure correct content type
            }

            if API_GATEWAY_URL == "YOUR_API_GATEWAY_ENDPOINT_URL_HERE/processfile" or API_KEY == "YOUR_API_KEY_HERE":
                st.error("API Gateway URL or API Key is not configured. Please set them in the script.")
                raise Exception("API not configured.")

            # Make API Call
            response = requests.post(API_GATEWAY_URL, json=payload, headers=headers, timeout=300) # 5 min timeout
            response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
            
            api_response_data = response.json()
            encoded_video_content = api_response_data.get("video_content")
            output_filename = api_response_data.get("filename", "video_output.mp4")

            timing_stats['steps']['api_call_duration'] = time.time() - api_call_start_time

            if encoded_video_content:
                video_bytes_content = base64.b64decode(encoded_video_content)
                
                st.success("Video processed successfully via API!")
                
                # Display video
                st.video(video_bytes_content)
                
                # Download button
                st.download_button(
                    label="Download Video",
                    data=video_bytes_content,
                    file_name=output_filename,
                    mime="video/mp4"
                )
                success = True
                message = f"Video '{output_filename}' processed and ready."
            else:
                st.error("API response missing video content or filename.")
                message = "API error: Response did not contain video content."

        except requests.exceptions.HTTPError as http_err:
            st.error(f"API request failed with HTTP status {http_err.response.status_code}: {http_err.response.text}")
            message = f"API request failed: HTTP {http_err.response.status_code}"
            if timing_stats['steps'].get('api_call_duration') is None: # Ensure duration is logged even on failure
                 timing_stats['steps']['api_call_duration'] = time.time() - api_call_start_time
        except requests.exceptions.RequestException as e:
            st.error(f"API request failed: {e}")
            message = f"API request failed: {e}"
            if timing_stats['steps'].get('api_call_duration') is None:
                 timing_stats['steps']['api_call_duration'] = time.time() - api_call_start_time
        except Exception as e: # Catch other errors like JSON parsing from response, base64 decoding
            st.error(f"An error occurred: {e}")
            message = f"An error occurred: {e}"
            if timing_stats['steps'].get('api_call_duration') is None:
                 timing_stats['steps']['api_call_duration'] = time.time() - api_call_start_time
        
        # Display timing statistics if the API call was attempted
        if 'api_call_duration' in timing_stats['steps']:
            timing_stats['total_time'] = time.time() - timing_stats['start_time']
            st.subheader("Processing Statistics")
            stats_df = pd.DataFrame({
                'Step': ['API Call Duration'],
                'Time (seconds)': [f"{timing_stats['steps']['api_call_duration']:.2f}"]
            })
            stats_df.loc[len(stats_df)] = ['Total App Time', f"{timing_stats['total_time']:.2f}"]
            st.table(stats_df)
            
            # Log timing statistics (optional, consider if needed with API)
            log_entry = f"\n{datetime.now()}\n"
            log_entry += f"File: {uploaded_file.name}\n"
            log_entry += f"API Call Duration: {timing_stats['steps']['api_call_duration']:.2f} seconds\n"
            log_entry += f"Total App Time: {timing_stats['total_time']:.2f} seconds\n"
            log_entry += "-" * 50
            
            # For Streamlit sharing, writing to a local log file might not be persistent or accessible.
            # Consider logging to a database or a more persistent store if detailed metrics are needed.
            # For now, we can print to console (which might appear in Streamlit logs if configured)
            print(log_entry) 
            # Example: saving to a temp file in Streamlit if needed, but not standard
            # temp_log_path = os.path.join(tempfile.gettempdir(), "app_processing_stats.log")
            # with open(temp_log_path, "a") as f_log:
            #     f_log.write(log_entry)

        if not success: # If any step failed
             st.warning(f"Processing was not fully successful. Last message: {message}")


# # Add a cleanup button # Removed as FileProcessor is no longer used locally
# if st.button("Clean Up Temporary Files"):
#     st.session_state.file_processor.cleanup()
#     st.success("Temporary files cleaned up successfully!")

# Add footer
st.markdown("---")
st.markdown("### About")
st.markdown("""
MusicSynth is a tool that converts sheet music (primarily MusicXML via API) into visual piano roll animations.
- **Processing is now handled by a backend API.**
- Ensure the API Gateway URL and API Key are correctly configured in the script for full functionality.
""")