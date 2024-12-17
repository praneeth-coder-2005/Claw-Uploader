# bot/services/progress_manager.py
import logging

class ProgressManager:
    def __init__(self):
        self.progress_messages = {}

    def add_task(self, task_id, data):
        self.progress_messages[task_id] = data

    def get_task(self, task_id):
        return self.progress_messages.get(task_id)

    def remove_task(self, task_id):
        if task_id in self.progress_messages:
            del self.progress_messages[task_id]

    def update_task_status(self, task_id, status):
        if task_id in self.progress_messages:
            self.progress_messages[task_id]["status"] = status

    def get_task_by_status(self, status):
        for task_id, data in self.progress_messages.items():
            if "status" in data and data["status"] == status:
                return task_id, data
        return None, None

    def get_cancel_flag(self, task_id):
        task = self.get_task(task_id)
        if task:
            return task.get("cancel_flag", False)
        return False

    def set_cancel_flag(self, task_id, value):
        task = self.get_task(task_id)
        if task:
            task["cancel_flag"] = value

    def set_message_id(self, task_id, message_id):
        task = self.get_task(task_id)
        if task:
            task["message_id"] = message_id
