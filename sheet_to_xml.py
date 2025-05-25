from google import genai

client = genai.Client(api_key="AIzaSyD-cl_73zIVHOzCVOdh1btxHFELuG95EOk")

my_file = client.files.upload(file="music2.jpg")

response = client.models.generate_content(
    model="gemini-2.5-flash-preview-04-17",
    contents=[my_file, "I’ve attached an image of sheet music. Please convert it into accurate and well-structured MusicXML format. Ensure all musical details—such as notes, rhythms, time signatures, key signatures, dynamics, articulations, and layout—are faithfully represented. The output should be valid MusicXML suitable for use in standard music notation software."]
    )

print(response.text)