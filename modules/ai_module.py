from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key= GROQ_API_KEY 
)

chat_history = []

def ask_ai(prompt):
    global chat_history
    try:
        chat_history.append({"role": "user", "content": prompt})

        if len(chat_history) > 10:
            chat_history = chat_history[-10:]

        messages = [
            {
                "role": "system", 
               "content": (
            "You are JARVIS, Tony Stark's sophisticated AI assistant. You are currently in my computer, awaiting suit integration."
            "Respond in English only, in one-two short sentence. Be concise, polite, and slightly sarcastic if appropriate."
            "Always address the user as Sir. Do not use any markdown symbols like * or #."
                )   
            }
        ] + chat_history

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=50, 
            temperature=0.7
        )
        
        answer = response.choices[0].message.content.strip()
        
        chat_history.append({"role": "assistant", "content": answer})
        
        return answer.replace("*", "").replace("#", "")
        
    except Exception as e:
        return f"Sir, a brief error occurred: {e}"
        
        
        
##        import google.generativeai as genai

## genai.configure(api_key="AIzaSyA2emgNMXJqR8lrY5Gj1CjH5nE5hRIVfe0")

##def ask_ai(prompt):
##    try:
##        model = genai.GenerativeModel('gemini-1.5-flash')
#        
 #       system_instruction = (
  #          "You are JARVIS, Tony Stark's sophisticated AI assistant. I trying to create you and now working with code. now you are in my computer, later uoy will be added in iron man suit. "
   #         "Respond in English only. Be concise, polite, and slightly sarcastic if appropriate. "
    #        "Never use Markdown symbols like asterisks (**) or hashes (#) in your text output. "
     #       "Always address the user as 'Sir'."
       # )
        
      #  full_prompt = f"{system_instruction}\n\nUser: {prompt}"
        
        #response = model.generate_content(full_prompt)
        
#        clean_text = response.text.replace("*", "").replace("#", "")
 #       return clean_text
  #  except Exception as e:
   #     return f"System error: {e}"