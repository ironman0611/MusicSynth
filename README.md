# MusicSynth - Serverless Sheet Music Visualizer

## Overview
MusicSynth is a tool that converts sheet music (primarily MusicXML files) into visual piano roll animations. This version utilizes a serverless backend powered by AWS Lambda and Amazon API Gateway. The Streamlit frontend sends file data to an API endpoint, which triggers a Lambda function to process the file and return a video.

The core processing logic, which involves parsing the music file and generating video frames, is now encapsulated within an AWS Lambda function. This allows for scalable, on-demand processing without needing to manage a dedicated server.

## Architecture
The application follows a simple serverless architecture:

```
Streamlit Frontend (app.py)
       |
       | (Uploads file data, encoded)
       v
Amazon API Gateway (HTTP API)
       |  (Requires API Key)
       |  (Triggers Lambda)
       v
AWS Lambda Function (lambda_handler.py)
       |  (Uses file_processor.py & synthesia.py)
       |  (Processes MusicXML, generates MP4)
       v
Video Result (MP4, encoded)
       |
       | (Returned to Streamlit App)
       v
Streamlit Frontend (Displays video)
```

## Prerequisites
To deploy and run this application, you will need:
- **AWS CLI:** Configured with appropriate credentials and a default region.
- **AWS SAM CLI:** The AWS Serverless Application Model Command Line Interface.
- **Python 3.9 or higher:** For the Streamlit frontend and Lambda function.
- **Docker (Recommended):** For `sam build --use-container`, which can help ensure consistency for Lambda deployment, especially if native dependencies are involved.
- **An AWS Account:** To deploy the resources.

## Project Structure
Key files and directories in this project:

-   `app.py`: The Streamlit frontend application.
-   `lambda_package/`: Contains all code and requirements for the AWS Lambda function.
    -   `lambda_handler.py`: The main handler for the Lambda function.
    -   `file_processor.py`: Handles file validation and processing orchestration.
    -   `synthesia.py`: Core logic for MusicXML parsing and video frame generation.
    -   `lambda_requirements.txt`: Python dependencies for the Lambda function.
-   `template.yaml`: The AWS SAM template that defines the serverless backend resources (Lambda, API Gateway, API Key).
-   `README.md`: This file.

## Deployment Instructions
Follow these steps to deploy the serverless backend to your AWS account:

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/yourusername/MusicSynth.git # Replace with your repo URL
    cd MusicSynth
    ```

2.  **Build the SAM Application:**
    This command compiles your Lambda function code and prepares it for deployment.
    ```bash
    sam build
    ```
    If you encounter issues with dependencies, especially those with native components (though current ones might not strictly need it), using a container can provide a cleaner build environment:
    ```bash
    sam build --use-container
    ```

3.  **Deploy the Application:**
    This command packages and deploys your application to AWS CloudFormation.
    ```bash
    sam deploy --guided
    ```
    You will be prompted for several parameters. Here are some key ones:
    *   **Stack Name:** A unique name for your CloudFormation stack (e.g., `musicsynth-prod`).
    *   **AWS Region:** The AWS region to deploy your application to (e.g., `us-east-1`).
    *   **Parameter MusicSynthApiStageName [prod]:** You can leave this as `prod` or specify another stage name.
    *   **Confirm changes before deploy:** Answer `Y` or `N`.
    *   **Allow SAM CLI IAM role creation:** Answer `Y`.
    *   **MusicSynthLambda may not have authorization defined:** Confirm with `Y` as we use an API Key for the HTTP API.
    *   **Save arguments to configuration file:** Answer `Y` to save your choices in `samconfig.toml` for future deployments.

4.  **Retrieve API Endpoint and API Key:**
    After a successful deployment, the SAM CLI will output several values. Note down:
    *   `MusicSynthApiEndpoint`: This is the base URL for your API Gateway (e.g., `https://abcdef123.execute-api.us-east-1.amazonaws.com/prod`).
    *   `MusicSynthApiKeyId`: This is the *ID* of the generated API Key (e.g., `zyxwvu987`).

    **Important: Getting the API Key Value**
    The `MusicSynthApiKeyId` is NOT the key value itself. To get the actual API key value needed by the client:
    *   Go to the AWS API Gateway console.
    *   Select your region.
    *   Navigate to "API Keys" in the left sidebar.
    *   Find the API key with the name `MusicSynthClientApiKey` or match the `MusicSynthApiKeyId` from the output.
    *   Click on the key name, and then click "Show" to reveal the API key value.
    *   **Copy this value securely.** This is what your Streamlit app will use.

5.  **Configure the Streamlit App (`app.py`):**
    Open the `app.py` file and update the following placeholder constants at the top of the file:
    ```python
    API_GATEWAY_URL = "YOUR_API_GATEWAY_ENDPOINT_URL_HERE/processfile"
    API_KEY = "YOUR_API_KEY_HERE"
    ```
    *   Replace `YOUR_API_GATEWAY_ENDPOINT_URL_HERE/processfile` with the `MusicSynthApiEndpoint` value you noted, ensuring you append `/processfile` (or your specific path if changed in `template.yaml`). For example: `https://abcdef123.execute-api.us-east-1.amazonaws.com/prod/processfile`.
    *   Replace `YOUR_API_KEY_HERE` with the actual API key *value* you retrieved from the API Gateway console.

    **Security Note:** For production or shared applications, **do not hardcode API keys directly in your code.** Use environment variables or Streamlit Secrets management:
    *   **Environment Variables:** Set `API_GATEWAY_URL` and `API_KEY` as environment variables where your Streamlit app runs.
    *   **Streamlit Secrets:** If deploying to Streamlit Community Cloud, use their secrets management feature (`st.secrets`).

## Running the Application

1.  **Ensure Backend is Deployed:** The AWS SAM deployment must be completed successfully.
2.  **Configure `app.py`:** Make sure `API_GATEWAY_URL` and `API_KEY` in `app.py` are updated with your deployment details.
3.  **Run the Streamlit Frontend:**
    ```bash
    streamlit run app.py
    ```
    This will start a local web server, and you can access the app in your browser (usually at `http://localhost:8501`).

The backend processing is now handled by AWS Lambda, triggered via API Gateway.

## Local Development & Testing

### Lambda Function Tests
The `lambda_handler.py` file contains an `if __name__ == '__main__':` block with a suite of local tests. You can run these to test the handler's logic directly:
```bash
python lambda_package/lambda_handler.py
```
This will execute various scenarios (valid file, missing parameters, etc.) and print results to the console. It creates a mock `synthesia.py` if the real one isn't fully functional locally due to dependencies.

### AWS SAM Local (Advanced)
For a more accurate local emulation of the Lambda environment and API Gateway, you can use `sam local`:

1.  **Invoke Lambda Locally:**
    You'll need an event payload file (e.g., `event.json`) that mimics the structure API Gateway sends to Lambda.
    ```bash
    sam local invoke MusicSynthLambda -e path/to/event.json
    ```
    (Ensure Docker is running if your function has dependencies that require it or if you use `--use-container` during build).

2.  **Start Local API Gateway:**
    ```bash
    sam local start-api
    ```
    This will start a local server emulating API Gateway, allowing you to send HTTP requests to `http://127.0.0.1:3000/processfile`. You'll need to pass the API key in the `x-api-key` header.

## Cleanup (AWS Resources)
To remove all the AWS resources created by this SAM application, delete the CloudFormation stack:
```bash
aws cloudformation delete-stack --stack-name <your-stack-name>
```
Replace `<your-stack-name>` with the name you provided during `sam deploy --guided` (e.g., `musicsynth-prod`). You can monitor the deletion progress in the AWS CloudFormation console.

## Dependencies (Lambda)
The Lambda function (`lambda_package/lambda_requirements.txt`) requires:
- `numpy`
- `Pillow`
- `moviepy`

Note: `moviepy` depends on `ffmpeg`. The default Python 3.9 Lambda runtime in AWS includes `ffmpeg`. If using a different runtime or encountering issues, a Lambda Layer or custom container image might be necessary to provide `ffmpeg`.

## License
This project is licensed under the terms of the included LICENSE file.

## Contributing
Contributions are welcome! Please feel free to submit a Pull Request.
```
