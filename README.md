1. Set up a Google Cloud Project:
a. Go to the Google Cloud Console (https://console.cloud.google.com/).
b. Create a new project or select an existing one.
c. Make note of your project ID.
2. Enable the Google Forms API:
a. In the Cloud Console, go to the "APIs & Services" dashboard.
b. Click on "+ ENABLE APIS AND SERVICES" at the top.
c. Search for "Google Forms API" and "Google Sheets API" then select it.
d. Click "Enable" to activate the API for your project.
3. Create credentials:
a. In the Cloud Console, go to the "APIs & Services" > "Credentials" page.
b. Click "Create Credentials" and select "OAuth client ID".
c. If prompted, configure the OAuth consent screen first.
d. For application type, choose "Web application" or "Desktop app" depending on your use case.
e. Add authorized redirect URIs if you're using a web application.
f. Click "Create" and download the client configuration file (JSON).
4. To use this code:
a. Enable APIs: Make sure you have enabled both the Google Sheets API and the Google Forms API in your Google Cloud Platform project.
b. Credentials: Download the client_secret.json file for your project from the Google Cloud Console.
c. Replace Placeholders: Replace the placeholders for sheet_url, sheet_id, selected_questions, and form_name with your actual data.
d. Run: Execute the Python script. It will handle authentication, fetch data, and generate the Google Form.
5. install the requirements by
pip install -r requirements.txt
6. change the variable CLIENT_SECRETS_FILE to the client configuration file (JSON) name you downloaded (in line 25 of app.py)
7. run app.py and open http://127.0.0.1:5000 to open the webpage

Note:
1. delete the token when it is expired
2. there is a bug that success form generation show an error alert in the page
3. Setting google form name is not working due to unknown reason
4. loadSheetv2 can also create form by revieving the link of sheet and question id (number) as input
