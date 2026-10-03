import sys


class WWOneTimeTask:

    def run(self):
        # Import Windows-specific helpers only when an actual one-time task
        # runs. This keeps task configuration and pure logic importable by
        # non-Windows tooling and unit tests.
        from src.task.MouseResetTask import MouseResetTask

        mouse_reset_task = self.executor.get_task_by_class(MouseResetTask)
        mouse_reset_task.run()
        PostMessageInteraction = None
        if sys.platform == 'win32':
            from ok import PostMessageInteraction
        if PostMessageInteraction and isinstance(self.executor.interaction, PostMessageInteraction):
            self.executor.interaction.activate()
        self.sleep(0.5)
