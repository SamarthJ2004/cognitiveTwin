import sys
import threading
from datetime import datetime
from pathlib import Path

import rumps
from dotenv import load_dotenv

from app.data_analysis import analyze
import app.db as db

load_dotenv()

USER_ID = sys.argv[1] if len(sys.argv) > 1 else "Samarth"
ICON = None

sys.path.insert(0, str(Path(__file__).parent))


class CognitiveTwin(rumps.App):

    def __init__(self):
        super().__init__(name="CognitiveTwin", title="◈", icon=ICON, quit_button=None)

        self.profile = None
        self.answers = None
        self.session = None

        self.menu = [
            rumps.MenuItem("Ask Twin", callback=self.ask_twin),
            rumps.MenuItem("Run Check-in", callback=self.run_checkin),
            None,
            rumps.MenuItem(f"User: {USER_ID}"),
            rumps.MenuItem("Status: Loading profile..."),
            None,
            rumps.MenuItem("Quit", callback=self.quit_app),
        ]

        self.load_profile()

    def load_profile(self):
        def worker():
            try:
                self.session = db.driver.session()
                db.ensure_user(self.session, USER_ID)
                self.profile = db.get_profile(self.session, USER_ID)
                # self.answers = db.get_raw_answers( self.session, USER_ID)
                self.menu["Status: Loading profile..."].title = ("Status: Ready")
            except Exception as e:
                self.menu["Status: Loading profile..."].title = ("Status: Error")
                print(f"profile load error: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def ask_twin(self, _):
        response = rumps.Window(
            title="Ask CognitiveTwin",
            message="Ask anything",
            default_text="",
            ok="Ask",
            cancel="Cancel",
            dimensions=(420, 120),
        ).run()

        if not response.clicked:
            return

        question = response.text.strip()

        if not question:
            return

        rumps.notification("CognitiveTwin", "", "Thinking...")

        threading.Thread(target=self._run_twin_query, args=(question,), daemon=True).start()

    def _run_twin_query(self, question):
        try:
            if not self.profile:
                rumps.notification(
                    title="Profile not ready",
                    subtitle="Profile not ready",
                    message="Wait a few seconds and try again."
                )
                return

            profile_text = db.format_profile(self.profile)
            answer = analyze.ask_twin(USER_ID, profile_text, question)
            timestamp = datetime.now().strftime("%H:%M")

            rumps.notification(title=f"Twin • {timestamp}", subtitle="Response Ready", message=answer)
        except Exception as e:
            rumps.notification(title="Error", subtitle="Twin query failed", message=str(e))

    def run_checkin(self, _):
        response = rumps.Window(
            title="Daily Check-in",
            message="What's on your mind today?",
            default_text="",
            ok="Save",
            cancel="Cancel",
            dimensions=(420, 120),
        ).run()

        if not response.clicked:
            return

        answer = response.text.strip()

        if not answer:
            return

        threading.Thread(target=self._save_checkin, args=(answer,), daemon=True).start()

    def _save_checkin(self, answer):
        try:
            session = db.driver.session()
            db.ensure_user(session, USER_ID)

            q_id = ("widget_checkin_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
            db.save_answer(
                session,
                USER_ID,
                q_id,
                "What's on your mind today?",
                answer,
                "widget_checkin"
            )
            session.close()
            rumps.notification("CognitiveTwin", "", "Check-in saved")
        except Exception as e:
            rumps.notification("CognitiveTwin", "Error", str(e))

    def quit_app(self, _):
        try:
            if self.session:
                self.session.close()
            db.driver.close()
        except Exception:
            pass

        rumps.quit_application()


def main():
    print(f"Starting CognitiveTwin for {USER_ID}")
    app = CognitiveTwin()
    app.run()


if __name__ == "__main__":
    main()
