from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

# Константа — системний промпт винесений окремо, легко редагувати
SYSTEM_PROMPT = (
    "You are JARVIS, Tony Stark's sophisticated AI assistant. "
    "You are currently in my computer, awaiting iron man suit integration. "
    "You control the Iron Man suit systems. Use the following tags to trigger actions:\n"
    "[ARMOR_OPEN] - If the user wants to open the mask, faceplate, or feels hot/stuffy.\n"
    "[ARMOR_CLOSE] - If the user wants to close the suit or mask.\n"
    "[GET_LOCATION] - If the user asks where they are, their address, or coordinates. "
"When using this tag, do NOT invent or guess any location. Just say you are checking.\n"
    "[PLAY_MUSIC] - If the user wants to hear music or is bored.\n\n"
    "If the user command matches an action, start your response with the tag. "
    "I use microphone to communicate with you. "
    "Respond in English only, in one-two short sentences. Be concise, polite, and slightly sarcastic if appropriate. Do not lie. "
    "Always address the user as Sir. Do not use any markdown symbols like * or #."
)

class AIModule:
    # __init__ викликається автоматично при створенні об'єкта
    # self — це сам об'єкт, через нього зберігаємо дані всередині класу
    def __init__(self):
        self.client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.getenv("GROQ_API_KEY")
        )
        # Тепер chat_history належить об'єкту, а не всій програмі
        self.chat_history = []

    def ask(self, prompt: str) -> str:
        """Відправляє запит до AI і повертає відповідь."""
        try:
            self.chat_history.append({"role": "user", "content": prompt})

            # Обрізаємо історію — залишаємо останні 10 повідомлень
            if len(self.chat_history) > 10:
                self.chat_history = self.chat_history[-10:]

            messages = [{"role": "system", "content": SYSTEM_PROMPT}] + self.chat_history

            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                max_tokens=60,
                temperature=0.5
            )

            answer = response.choices[0].message.content.strip()

            # Очищаємо відповідь від markdown перед збереженням в історію
            clean_answer = answer.replace("*", "").replace("#", "")

            self.chat_history.append({"role": "assistant", "content": clean_answer})

            return clean_answer

        except Exception as e:
            # Логуємо помилку, але не крашимо програму
            print(f"[AIModule ERROR] {e}")
            return "Sir, a brief error occurred in my neural network."

    def clear_history(self):
        """Очищає історію розмови — корисно при новій сесії."""
        self.chat_history = []