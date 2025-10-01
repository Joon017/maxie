import json
from openai import OpenAI
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class ConversationState:
    def __init__(self):
        self.sessions = {}
        self.stage_priority = {
            # Intro
            "intro-warm": 0,
            "intro-cold": 0,

            # Discovery
            "discovery-open": 1,
            "discovery-specific": 2,

            # Qualification
            "qualification-budget": 3,
            "qualification-goal": 3,

            # Consideration
            "considering-price": 4,
            "considering-fit": 4,

            # Conversion
            "conversion-implicit": 5,
            "conversion-explicit": 6,

            # Objections
            "objection-price": 3.5,
            "objection-need": 3.5,
            "objection-time": 3.5,

            # Post-pitch granular
            "post-pitch-hesitation": 4.2,
            "post-pitch-curiosity": 4.3,
            "post-pitch-slight-interest": 4.4,
            "post-pitch-soft-confirmation": 4.5,
            "post-pitch-backtracking": 4.1,
            "post-pitch-encouragement-needed": 4.6,

            # Closure
            "closed-success": 7,
            "closed-soft-rejection": 7,
            "closed-hard-rejection": 7,

            # Follow-up
            "followup-checkin": 8,
            "followup-upgrade": 8
        }

        self.substage_scores = {
            "discovery-open": 2,
            "discovery-specific": 3,
            "qualification-budget": 2,
            "qualification-goal": 2,
            "considering-price": 2,
            "considering-fit": 3,
            "conversion-implicit": 4,
            "conversion-explicit": 5,
            "objection-price": 1,
            "objection-need": 1,
            "objection-time": 1,
            "post-pitch-hesitation": -1,
            "post-pitch-curiosity": 1,
            "post-pitch-slight-interest": 1,
            "post-pitch-soft-confirmation": 2,
            "post-pitch-encouragement-needed": 2,
            "post-pitch-backtracking": -2,
            "closed-soft-rejection": -3,
            "closed-hard-rejection": -5,
            "followup-checkin": 1,
            "followup-upgrade": 2
        }

    def init_session(self, session_id):
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "stage": "intro-warm",
                "latest_substage": "intro-warm",
                "score": 0,
                "cta_recommended": False,
                "last_cta_shown": None,
                "messages_exchanged": 0
            }

    def extract_json_object(self, text):
        import re
        match = re.search(r'\{[^}]+\}', text)
        return match.group(0) if match else '{}'

    def infer_stage_gpt(self, message, context_summary):
        prompt = f"""
    You are a meticulous **conversation stage analyst AI** working for a solopreneur's assistant. 

    Your job is to classify the user's current conversation **substage** using the provided message and context.

    ---

    🎯 **Your classification must be from the list below.**

    Each substage reflects a specific moment in the user's psychological journey toward buying something.

    Only return a JSON object like:
    {{ "substage": "conversion-explicit" }}

    ---

    📘 **Substage Definitions**:

    - **intro-warm**: Casual greeting or friendly start (e.g., "hey there", "hi!")
    - **intro-cold**: Neutral or uncertain entry (e.g., "what is this?", "who are you?")
    - **discovery-open**: Asking broad questions, unsure of options (e.g., "what do you offer?")
    - **discovery-specific**: Asking focused product/service questions (e.g., "is Dior Sauvage tea-based?")
    - **qualification-budget**: Mentions or inquires about cost or affordability.
    - **qualification-goal**: Reveals intent or desired outcome (e.g., "I want to gift something for my brother")
    - **considering-price**: Expresses curiosity or concern about pricing, but still open.
    - **considering-fit**: Evaluating personal relevance, suitability, or preferences.
    - **conversion-implicit**: Suggests intent without clear action (e.g., "I might get it", "this sounds good")
    - **conversion-explicit**: Direct commitment (e.g., "I’ll buy it", "add to cart", "I want this one")
    - **objection-price**: Pushback or concern about cost (e.g., "that’s too expensive")
    - **objection-need**: Uncertainty about necessity (e.g., "do I really need this?")
    - **objection-time**: Concern about timing or urgency (e.g., "maybe later", "not now")
    - **post-pitch-hesitation**: Indecisive or delaying (e.g., "let me think", "I’m not sure")
    - **post-pitch-curiosity**: Asking follow-ups out of interest, not doubt (e.g., "what else do you offer?")
    - **post-pitch-slight-interest**: Subtle signs of interest, vague leaning (e.g., "sounds interesting")
    - **post-pitch-soft-confirmation**: Mild affirmation without action (e.g., "ok I like it")
    - **post-pitch-backtracking**: Pulling away after positive signals (e.g., "on second thought...")
    - **post-pitch-encouragement-needed**: Implied desire but needs push (e.g., "I just need help choosing")
    - **closed-success**: Clear purchase or final commitment (e.g., "just bought it", "I placed the order")
    - **closed-soft-rejection**: Gentle no (e.g., "maybe not now", "not sure if it's for me")
    - **closed-hard-rejection**: Direct refusal (e.g., "no thanks", "not interested")
    - **followup-checkin**: Returning after past interest (e.g., "hey, just checking again")
    - **followup-upgrade**: Looking to buy more or upgrade (e.g., "can I get a larger version?")

    ---

    🚫 **Rules**:

    - Do **not** classify as "closed-success" unless the message confirms the purchase happened or will happen very soon.
    - If the message uses soft intent ("maybe", "might", "probably", "I guess"), lean toward:
    - `conversion-implicit`
    - `post-pitch-soft-confirmation`
    - If unsure, always choose the **most conservative possible** substage.
    - Don't just guess based on tone. Context and specificity matter.

    ---

    📝 **Context**:
    {context_summary}

    💬 **Latest User Message**:
    {message.strip()}

    🔚 Return only a JSON object like:
    {{ "substage": "..." }}
    """

        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": prompt}],
                temperature=0
            )
            content = response.choices[0].message.content.strip()
            print("[Stage inference raw response]", content)
            parsed = json.loads(self.extract_json_object(content))
            return parsed.get("substage", "intro-warm")

        except Exception as e:
            print("Stage inference failed:", e)
            return "intro-warm"

    def update(self, session_id, intent, message, context_summary):
        self.init_session(session_id)
        state = self.sessions[session_id]
        state["messages_exchanged"] += 1

        # 🔍 GPT infers latest substage
        inferred_substage = self.infer_stage_gpt(message, context_summary)

        # ✅ Sanity check: only accept valid substages
        if inferred_substage not in self.stage_priority:
            print(f"⚠️ Unrecognized substage from GPT: '{inferred_substage}', defaulting to 'intro-cold'")
            inferred_substage = "intro-cold"

        previous_stage = state.get("stage", "intro-warm")
        previous_substage = state.get("latest_substage", "intro-warm")

        # 🧠 Always update latest_substage to reflect present behavior
        state["latest_substage"] = inferred_substage

        # 🔁 Only upgrade cumulative stage if this substage is more advanced
        current_priority = self.stage_priority.get(previous_stage, 0)
        new_priority = self.stage_priority.get(inferred_substage, 0)

        # 🔁 Allow interruption by objection or hesitation stages even if lower priority
        if "objection" in inferred_substage or "post-pitch" in inferred_substage:
            print(f"⚠️ Interrupting with substage: {inferred_substage}")
            state["stage"] = inferred_substage
        elif new_priority > current_priority:
            state["stage"] = inferred_substage
        else:
            print("➖ No stage update (lower priority and not an objection/post-pitch)")

        # 🎯 Update engagement score based on current behavioral signal
        delta = self.substage_scores.get(inferred_substage, 0)
        state["score"] += delta

        # 📊 Print debug info
        print(f"\n🧠 [Conversation State]")
        print(f"User Intent: {intent}")
        print(f"New message: {message}")
        print(f"Inferred substage: {inferred_substage}")
        print(f"Previous substage: {previous_substage}")
        print(f"Updated stage: {state['stage']} (priority: {self.stage_priority[state['stage']]})")
        print(f"📊 Engagement Score: {state['score']} | Messages: {state['messages_exchanged']}")


    def get_state(self, session_id):
        self.init_session(session_id)
        return self.sessions[session_id]
