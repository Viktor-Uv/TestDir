import openai, telebot, json, time, requests
from openai.error import OpenAIError

# Set up Telegram Bot credentials
bot = telebot.TeleBot("BOT_API", threaded=False)
# Set up OpenAI API credentials
openai.api_key = "AI_API"
# Define default parameters
DEF_TEMP = 1
MAX_TEMP = 2
MAX_DIALOG_SIZE = 5
MIN_CHARACTERS = 250
SMALL = "256x256"
MEDIUM = "512x512"
BIG = "1024x1024"
# Load existing user data from file
try:
    # Read the JSON object
    with open('data.json', 'r') as f:
        data = json.load(f)
except FileNotFoundError:
    data = {}


def lambda_handler(event, context):
    update = telebot.types.Update.de_json(json.loads(event['body']))
    bot.process_new_updates([update])
    return  {
        'statusCode': 200
    }


# Function to generate response using OpenAI API
def generate_response(dialog, request, id):
    # Generate AI responce
    knowledge_cutoff = "Up to Sep 2021"
    time_now = time.gmtime()
    current_time = time.strftime("%a, %d-%b-%Y %H:%M UTC", time_now)
    system_msg = [{"role": "system", "content": f"Your name is Chatter. You are a friendly Telegram bot. You were created by Viktor Uvarchev. You generate text using OpenAI API. Knowledge cutoff: {knowledge_cutoff}. Current date and time: {current_time}. You can generate text when user talks to you and generate images when user sends /imagine command, suggest to use '/help' for list of commands"}]
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=system_msg + dialog + request,
            temperature=data[id]["Temp"],
            max_tokens=1024
        )
    except OpenAIError as e:
        return f"OpenAI error...\nCode: {e.http_status}\nMessage: {e.user_message}\n{e.headers['Date']}"
    # Return AI generated reply
    return response["choices"][0]["message"]["content"]


@bot.message_handler(commands=['temp'])
def set_temperature(message):
    # Take ID of a group or person
    id = str(message.chat.id)
    # Initialise new id, if it doesn't exist
    initialise(id, message)
    # If empty parameter given - show current set value
    if len(message.text.split()) == 1:
        bot.reply_to(message, f"""Parameter "temperature" is currently set to {data[id]["Temp"]}""")
    else:
        # Extract parameter from the message
        try:
            temp = float(message.text.split()[1])
        except:
            # Remind proper usage example
            bot.reply_to(message, f"""Usage: "/temp temperature" (0 to {MAX_TEMP})""")
            return
        # Check usage
        if temp >= 0 and temp <= MAX_TEMP:
            # Indicate success
            data[id]["Temp"] = temp
            bot.reply_to(message, f"""Parameter "temperature" is now set to {temp}""")
        else:
            # Indicate usage error
            bot.reply_to(message, f"""Usage: "/temp temperature" (0 to {MAX_TEMP})""")
    # Update data file
    write_data()


@bot.message_handler(commands=['imagine'])
def image_generation(message):
    # Take ID of a person and initialise, then increment the request count
    id = str(message.from_user.id)
    initialise(id, message)
    data[id]["AI_Requests"] += 1
    # If empty parameter given - show usage instructions
    if len(message.text.split()) == 1:
        bot.reply_to(message, """Usage: "/imagine description".""")
    else:
        # Remove '/imagine' from the message
        try:
            request = ' '.join(message.text.split()[1:])
        except:
            # Show usage instructions
            bot.reply_to(message, """Usage: "/imagine description".""")
            return
        try:
            response = openai.Image.create(
                prompt=request,
                n=1,
                size=MEDIUM
                )
            image_url = response['data'][0]['url']
            # Download the image from the URL
            image_content = requests.get(image_url).content
            # Send it to chat
            bot.send_photo(chat_id=message.chat.id, photo=image_content, reply_to_message_id=message.message_id)
            # Update data file
            write_data()
        except OpenAIError as e:
            bot.reply_to(message, f"OpenAI error...\nCode: {e.http_status}\nMessage: {e.user_message}\n{e.headers['Date']}")
            return


# Clears bot's memory
@bot.message_handler(commands=['clear'])
def send_welcome(message):
    # Take ID of a group or person
    id = str(message.chat.id)
    data[id]["Dialog"] = []
    bot.reply_to(message, "Memory erased.")
    # Update data file
    write_data()

@bot.message_handler(commands=['start'])
def send_start(message):
    bot.reply_to(message, "Hello, I'm your new bot!")


@bot.message_handler(commands=['hello'])
def greet_user(message):
    # Get the user's first name
    first_name = message.from_user.first_name
    # Greet the user by name or with a default message if the first name can't be retrieved
    if first_name:
        bot.reply_to(message, f"Hello, {first_name}!")
    else:
        bot.reply_to(message, "Hello there!")


@bot.message_handler(commands=['help'])
def help_user(message):
    # Print brief help
    bot.reply_to(message, f"""Reply to my message with any text to get an AI response\n
Use "/temp number" to set the "temperature" (between 0 and {MAX_TEMP}, default is {DEF_TEMP}). """ + \
"""Higher values will make the output more random, while lower values will make it more """ + \
"""focused and deterministic. Using without parameter will display the "temperature" currently set\n
Use "/imagine description" to get an AI generated image\n
Use "/clear" to clear Bot's memory\n
Use "/start" for a welcome message\n
Use "/hello" to be greeted\n\n
Commands are case-sensitive!""")


@bot.message_handler(func=lambda message: True, content_types=['text'])
def echo_message(message):
    # Take ID of a person and initialise, then increment the request count
    id = str(message.from_user.id)
    initialise(id, message)
    data[id]["AI_Requests"] += 1
    # Take ID of a group or person and rewrite the above person ID
    id = str(message.chat.id)
    initialise(id, message)
    # Reply to the chat
    request = [{"role": "user", "content": message.text}]
    dialog = data[id]["Dialog"]
    response = generate_response(dialog, request, id)
    try:
        bot.reply_to(message, response)
    except Exception as e:
        print(bot.reply_to(message, f"Telegram Bot error...\nMessage: {e.args[0]}\n{e.result.headers['Date']}"))
    # Save dialog
    dialog += [{"role": "user", "content": shorten(message.text)},
               {"role": "assistant", "content": shorten(response)}]
    dialog = shorten_dialog(dialog)
    data[id]["Dialog"] = dialog
    # Update data file
    write_data()


# Generate dialog of the MAX_DIALOG_SIZE from the past requests
def shorten_dialog(dialog):
    # If the dialog size exceeds the maximum, remove the oldest request/response pair
    if len(dialog) > MAX_DIALOG_SIZE * 2:
        dialog.pop(0)
        dialog.pop(0)
    # Concatenate response
    return dialog


def shorten(text):
    shortened = ""
    for i in range(len(text)):
        if i > MIN_CHARACTERS and text[i] in ['.', '?', '!', '\n']:
            shortened += text[i]
            break
        else:
            shortened += text[i]
    return shortened


def initialise(id, message):
    if id not in data:
        if int(id) >= 0:
            nickname = message.from_user.username
            data[id] = {
                "User_name": message.from_user.full_name,
                "Nick": "" if nickname is None else nickname,
                "Dialog": [],
                "Temp": DEF_TEMP,
                "AI_Requests": 0
            }
        else:
            chat_info = bot.get_chat(id)
            data[id] = {
                "Group_name": chat_info.title,
                "Dialog": [],
                "Temp": DEF_TEMP
            }


def write_data():
    with open('data.json', 'w') as f:
        json.dump(data, f)
