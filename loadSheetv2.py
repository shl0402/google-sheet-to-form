import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/forms.body', 'https://www.googleapis.com/auth/spreadsheets.readonly']

CATEGORIES_TO_FILTER = ['Subject', 'Topic', 'Subtopic', 'Difficulty']

CLIENT_SECRETS_FILE = "client_secret_374818502051-20nosim2fh9d67680l0dta6e0nvtmg0i.apps.googleusercontent.com.json"

def get_credentials():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds

def fetch_sheet_data(sheet_url):
    creds = get_credentials()
    service = build('sheets', 'v4', credentials=creds)

    # Extract the spreadsheet ID from the URL
    sheet_id = sheet_url.split('/')[5]

    # Call the Sheets API
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=sheet_id, range='A1:Z').execute()
    values = result.get('values', [])

    if not values:
        print('No data found.')
        return []

    return values

def create_category_hierarchy(data):
    headers = data[0]
    subject_index = next((i for i, h in enumerate(headers) if h.lower() == 'subject'), -1)
    topic_index = next((i for i, h in enumerate(headers) if h.lower() == 'topic'), -1)
    subtopic_index = next((i for i, h in enumerate(headers) if h.lower() == 'subtopic'), -1)

    category_hierarchy = {
        'subjects': set(),
        'topics': set(),
        'subtopics': set(),
        'subject_to_topic': {},
        'topic_to_subtopic': {}
    }

    for row in data[1:]:
        subject = row[subject_index].lower()
        topic = row[topic_index].lower()
        subtopic = row[subtopic_index].lower()

        category_hierarchy['subjects'].add(subject)
        category_hierarchy['topics'].add(topic)
        category_hierarchy['subtopics'].add(subtopic)

        if subject not in category_hierarchy['subject_to_topic']:
            category_hierarchy['subject_to_topic'][subject] = set()
        category_hierarchy['subject_to_topic'][subject].add(topic)

        if topic not in category_hierarchy['topic_to_subtopic']:
            category_hierarchy['topic_to_subtopic'][topic] = set()
        category_hierarchy['topic_to_subtopic'][topic].add(subtopic)

    return category_hierarchy

def extract_questions(data):
    headers = data[0]
    question_index = next((i for i, h in enumerate(headers) if h.lower() == 'question'), -1)
    question_id_index = next((i for i, h in enumerate(headers) if h.lower() == 'question id'), -1)
    answer_index = next((i for i, h in enumerate(headers) if h.lower() == 'correct answer'), -1)
    options_index = next((i for i, h in enumerate(headers) if h.lower() == 'answer options'), -1)

    if question_index == -1 or question_id_index == -1:
        print("Error: 'Question' or 'Question ID' column not found in the sheet.")
        return []

    questions = []
    for row in data[1:]:  # Skip the header row
        question_data = {}
        for i, header in enumerate(headers):
            if i < len(row):  # Check if the row has enough columns
                question_data[header.lower()] = row[i]
            else:
                question_data[header.lower()] = ''  # Add empty string if column is missing
        
        # Process options if present
        if options_index != -1 and options_index < len(row) and row[options_index].strip():
            options = row[options_index].split('||')
            question_data['options'] = [option.strip() for option in options if option.strip()]
        
        # Process correct answer
        if answer_index != -1 and answer_index < len(row):
            correct_answer = row[answer_index].strip()
            question_data['correct_answer'] = correct_answer
            
            # Check if the correct answer is in the options
            if 'options' in question_data and correct_answer not in question_data['options']:
                print(f"Warning: Correct answer '{correct_answer}' not found in options for question: {question_data.get('question', 'Unknown')}")
        
        questions.append(question_data)

    print("questions")
    print(questions)
    return questions


import json

def add_question_to_form(forms_service, form_id, question):
    try:
        if 'question' not in question or not question['question'].strip():
            return False, "Question text is missing"

        question_type = "TEXT" if 'options' not in question or not question['options'] else "MULTIPLE_CHOICE"
        
        if question_type == "MULTIPLE_CHOICE":
            options = question.get('options', [])
            correct_answer = question.get('correct_answer', '')
            
            # Check if options are empty
            if not options:
                return False, "No options provided for multiple-choice question"
            
            # Check if correct answer is in options
            if correct_answer not in options:
                return False, "Correct answer is not in the options"
            
            # Remove duplicate options
            options = list(dict.fromkeys(options))
            
            new_question = {
                "requests": [{
                    "createItem": {
                        "item": {
                            "title": question['question'],
                            "questionItem": {
                                "question": {
                                    "required": True,
                                    "grading": {
                                        "pointValue": 1,
                                        "correctAnswers": {
                                            "answers": [{"value": correct_answer}]
                                        },
                                        "whenRight": {"text": "Correct!"},
                                        "whenWrong": {"text": "Sorry, that's incorrect."}
                                    },
                                    "choiceQuestion": {
                                        "type": "RADIO",
                                        "options": [{"value": option} for option in options],
                                        "shuffle": False
                                    }
                                }
                            },
                        },
                        "location": {"index": 0}
                    }
                }]
            }

        else:
            new_question = {
                "requests": [{
                    "createItem": {
                        "item": {
                            "title": question['question'],
                            "questionItem": {
                                "question": {
                                    "required": True,
                                    "textQuestion": {
                                        "paragraph": True
                                    }
                                }
                            }
                        },
                        "location": {"index": 0}
                    }
                }]
            }

        # Create the question
        response = forms_service.forms().batchUpdate(formId=form_id, body=new_question).execute()
        
        # Extract the question ID
        if 'replies' in response and response['replies']:
            reply = response['replies'][0]
            if 'createItem' in reply:
                create_item = reply['createItem']
                if 'questionId' in create_item:
                    question_id = create_item['questionId'][0]  # The questionId is now an array
                    return True, question_type
                else:
                    return False, "Question ID not found in response"
            else:
                return False, "CreateItem not found in response"
        else:
            return False, "Replies not found in response"

    except HttpError as error:
        return False, f"An error occurred: {error}"
    

def main():
    creds = get_credentials()
    forms_service = build('forms', 'v1', credentials=creds)

    # Fetch Google Sheet data
    sheet_url = input("Enter the Google Sheet URL: ")
    data = fetch_sheet_data(sheet_url)

    # Extract questions with their categories
    questions = extract_questions(data)

    # Print some information
    print("Google Sheet data loaded successfully.")
    print(f"Number of rows: {len(data)}")
    print(f"Number of columns: {len(data[0])}")

    # Print questions with their categories
    print("\nQuestions with categories:")
    for i, question in enumerate(questions, 1):
        print(f"\nQuestion {i} (ID: {question.get('question id', 'N/A')}):")
        for category, value in question.items():
            if category != 'options':
                print(f"  {category}: {value}")
        if 'options' in question:
            print(f"  Options: {', '.join(question['options'])}")

    # Allow user to select questions
    selected_indices = input("\nEnter the numbers of the questions you want to add (e.g., 1 3 5 7): ").split()
    selected_indices = [int(index) - 1 for index in selected_indices if index.isdigit()]

    # Prompt for form title
    form_title = input("\nEnter the title for your new form: ")

    # Create a new Google Form with the specified title
    NEW_FORM = {
        "info": {
            "title": form_title,
        }
    }
    result = forms_service.forms().create(body=NEW_FORM).execute()
    form_id = result['formId']

    # Update the form to be a quiz
    update_request = {
        "requests": [
            {
                "updateSettings": {
                    "settings": {
                        "quizSettings": {
                            "isQuiz": True
                        }
                    },
                    "updateMask": "quizSettings.isQuiz"
                }
            }
        ]
    }
    forms_service.forms().batchUpdate(formId=form_id, body=update_request).execute()

    form_url = f"https://docs.google.com/forms/d/{form_id}/edit"
    print(f"\nCreated quiz form with ID: {form_id}")
    print(f"Form URL: {form_url}")

    # Add selected questions to the form
    mc_success_list = []
    long_success_list = []
    error_list = []
                
    for index in selected_indices:
        if 0 <= index < len(questions):
            question = questions[index]
            success, result = add_question_to_form(forms_service, form_id, question)
            if success:
                if result == "MULTIPLE_CHOICE":
                    mc_success_list.append(question['question id'])
                else:
                    long_success_list.append(question['question id'])
            else:
                error_list.append((question['question id'], result))

    # Print results
    print("\nResults:")
    print(f"Successfully added multiple-choice questions (IDs): {', '.join(map(str, mc_success_list))}")
    print(f"Successfully added long-answer questions (IDs): {', '.join(map(str, long_success_list))}")
    print("Questions that could not be added:")
    for question_id, error_message in error_list:
        print(f"  Question ID {question_id}: {error_message}")

    print(f"\nTotal questions added: {len(mc_success_list) + len(long_success_list)}")
    print(f"Total errors: {len(error_list)}")
    print(f"\nForm URL: https://docs.google.com/forms/d/{form_id}/edit")

if __name__ == '__main__':
    main()