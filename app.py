from flask import Flask, redirect, url_for, session, request, jsonify, render_template, send_from_directory
from googleapiclient.discovery import build
from flask_session import Session
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.cloud import language_v1
from google.cloud.language_v1 import types
from google.oauth2 import service_account
from google.cloud import translate_v2 as translate
import openai
import os
import base64
import time
import json
import datetime
import re
from bs4 import BeautifulSoup
from operator import itemgetter



app = Flask(__name__)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
os.environ['PATH'] += os.pathsep + '/Users/matt/downloads/google-cloud-sdk/bin'
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/Users/matt/downloads/vaulted-bus-383605-bcb39e1c743c.json'
openai.api_key = "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"


# Define the scopes that you need for the Gmail API
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.compose']

# Create the flow object and specify the scopes
flow = InstalledAppFlow.from_client_secrets_file(
    'client_secret.json', scopes=SCOPES, redirect_uri="http://127.0.0.1:5000/callback")

'''def check_redirect_uri(flow):
    expected_redirect_uri = "http://localhost:5000/callback"
    actual_redirect_uri = flow.redirect_uri

    if actual_redirect_uri != expected_redirect_uri:
        return False
    return True'''
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
Session(app)

def clean_text(text):
    # Remove HTML tags
    soup = BeautifulSoup(text, 'html.parser')
    text = soup.get_text()

    # Remove URLs
    text = re.sub(r'http[s]?://\S+', '', text)

    # Remove email addresses
    text = re.sub(r'\S*@\S*\s?', '', text)

    # Remove special characters, numbers, and punctuations
    text = re.sub(r'[^a-zA-Z\s]', '', text)

    # Convert text to lowercase
    text = text.lower()

    # Optional: perform additional cleaning operations (e.g., tokenization, stop words removal, etc.)

    return text

language_client = language_v1.LanguageServiceClient()

def get_emails_data():
    ...
    email_data = []
    for message in messages:
        ...
    email_data.sort(key=lambda x: sum([info[1] for info in x['key_information']]), reverse=True)

    return email_data

def extract_key_information(text):
    document = types.Document(
        content=text,
        type_=language_v1.Document.Type.PLAIN_TEXT)

    response = language_client.analyze_entities(document=document)

    key_information = []
    for entity in response.entities:
        key_information.append((entity.name, entity.salience))

    return key_information

def generate_summary(key_information, max_entities=3):
    summary = []

    # Sort the key information by salience in descending order
    sorted_key_information = sorted(key_information, key=itemgetter(1), reverse=True)

    # Select the top N entities
    top_entities = sorted_key_information[:max_entities]

    # Create the summary
    for entity in top_entities:
        summary.append(entity[0])

    # Join the summary elements into a single string
    summary_text = ', '.join(summary)

    return summary_text

def generate_summary2(text):
    prompt = f"Rewrite a summary of the following email: {text}"
    response = openai.Completion.create(
        engine="text-davinci-002",
        prompt=prompt,
        max_tokens=50,
        n=1,
        stop=None,
        temperature=0.7,
    )

    summary = response.choices[0].text.strip()
    return summary

# Modify your index() function
@app.route('/')
def index():
    breakpoint()  # Add a breakpoint here

    # Check if the user has authorized the application
    if 'credentials' not in session:
        # If the user has not authorized the application, redirect to the OAuth2 consent screen
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true'
        )
        session['state'] = state

        return redirect(authorization_url)
    else:
        # If the user has already authorized the application, display the emails
        print("Authorized user, redirecting to get_emails")
        return get_emails()


# Get a list of the user's emails
@app.route('/emails')
def get_emails():
    # Check if the user has authorized the application
    if 'credentials' not in session:
        return redirect(url_for('index'))

    # Load the user's credentials from the session
    credentials = Credentials.from_authorized_user_info(session['credentials'])
    
    # Create a Gmail API client
    service = build('gmail', 'v1', credentials=credentials)

    # Get a list of the user's email messages from the last 24 hours
    yesterday = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).strftime('%Y/%m/%d')
    query = f"after:{yesterday}"
    result = service.users().messages().list(userId='me', q=query).execute()
    messages = result.get('messages', [])

    # Iterate over the messages and get their contents
    email_data = []
    for message in messages:
        msg = service.users().messages().get(userId='me', id=message['id']).execute()
        payload = msg['payload']
        headers = payload['headers']

        # Get the email subject and body text
        for header in headers:
            if header['name'] == 'Subject':
                subject = header['value']
            if header['name'] == 'From':
                sender = header['value']
            if header['name'] == 'Date':
                date = header['value']
        if 'parts' in payload:
            parts = payload['parts']
            data = ''
            for part in parts:
                if part['mimeType'] == 'text/plain':
                    if 'data' in part['body']:
                        data = part['body']['data']
                        break
            if data == '':
                if 'data' in payload['body']:
                    data = payload['body']['data']
        else:
            if 'data' in payload['body']:
                data = payload['body']['data']
            else:
                data = ''

        # Decode the email body text
        decoded_data = base64.urlsafe_b64decode(data.encode('utf-8')).decode('utf-8')
        cleaned_data = clean_text(decoded_data)
        key_information = extract_key_information(cleaned_data)
        summary = generate_summary2(key_information)

        # Add the email data to the list of emails
        email_data.append({
            'subject': subject,
            'sender': sender,
            'date': date,
            'body': cleaned_data,
            'key_information': key_information,
            'summary': summary,
        })
    email_data.sort(key=lambda x: sum([info[1] for info in x['key_information']]), reverse=True)
    
    # Render the emails template with the email data
    return render_template('emails.html', email_data=email_data)

@app.route('/download')
def download():
    return send_from_directory(os.getcwd(), 'email_summaries.json', as_attachment=True)

@app.route('/callback')
def callback():
    print("Inside the /callback function")
    print("Request URL:", request.url)


    breakpoint()  # Add a breakpoint here

    # Check if there's an error in the URL
    if 'error' in request.args:
        error_message = request.args.get('error')
        return f"Error: {error_message}"
    # Exchange the authorization code for a token
    flow.fetch_token(authorization_response=request.url)
    # Save the user's credentials in the session
    credentials = flow.credentials
    session['credentials'] = json.loads(credentials.to_json())

    # Redirect the user to the / page
    print("Redirecting to index route")
    return redirect(url_for('index'))

@app.route('/newsletter')
def newsletter():
    # Check if the user has authorized the application
    if 'credentials' not in session:
        return redirect(url_for('index'))

    email_data = get_emails_data()

    # Use the fetched email data to populate the newsletter sections
    top_emails = email_data[:5]  # Select the top 5 emails based on key information
    flash_news = email_data[5:10]  # Select the next 5 emails for flash news

    # Render the newsletter template with the email data
    return render_template('newsletter.html', top_emails=top_emails, flash_news=flash_news)



if __name__ == '__main__':
    app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev')
    app.run(debug=True)
