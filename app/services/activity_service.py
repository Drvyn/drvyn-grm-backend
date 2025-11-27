from app.models.activity import ActivityLog

async def log_activity(workshop_id: str, title: str, icon: str):
    """
    Creates and saves a new activity log entry.
    """
    try:
        activity = ActivityLog(
            workshop_id=workshop_id,
            title=title,
            icon=icon
        )
        await activity.insert()
    except Exception as e:
        # In a production app, you might want to log this error
        # but not fail the main request.
        print(f"Failed to log activity: {e}")