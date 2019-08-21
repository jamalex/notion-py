from .utils import now


def build_operation(id, path, args, command="set", table="block"):
    """
    Data updates sent to the submitTransaction endpoint consist of a sequence of "operations". This is a helper
    function that constructs one of these operations.
    """

    if isinstance(path, str):
        path = path.split(".")

    return {"id": id, "path": path, "args": args, "command": command, "table": table}


def operation_update_last_edited(user_id, block_id):
    """
    When transactions are submitted from the web UI, it also includes an operation to update the "last edited"
    fields, so we want to send those too, for consistency -- this convenience function constructs the operation.
    """
    return {
        "args": {"last_edited_by": user_id, "last_edited_time": now()},
        "command": "update",
        "id": block_id,
        "path": [],
        "table": "block",
    }
