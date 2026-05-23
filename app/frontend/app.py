import rumps


class MyApp(rumps.App):
    def __init__(self):
        super().__init__("Hello")

    @rumps.clicked("Say Hi")
    def say_hi(self, _):
        rumps.notification(
            "Rumps App",
            "Notification",
            "Hello from macOS menu bar!"
        )


MyApp().run()
