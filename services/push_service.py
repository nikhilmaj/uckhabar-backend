"""
UCKhabar — Push Notification Service (Firebase Cloud Messaging)

Handles background push notifications for:
1. Topic broadcasts ("breaking_news") without "Breaking News:" prefix.
2. Individual user alerts when their scheduled morning/afternoon/evening feed is ready.
"""
import logging
from typing import List, Optional
import firebase_admin
from firebase_admin import messaging

logger = logging.getLogger("uckhabar.push")

async def subscribe_token_to_topics(token: str, topics: List[str] = ["breaking_news"]) -> None:
    """Subscribe a web push FCM token to FCM topics like 'breaking_news'."""
    if not token:
        return
    for topic in topics:
        try:
            response = messaging.subscribe_to_topic([token], topic)
            logger.info(f"[Push] Subscribed token to topic {topic}: {response.success_count} success")
        except Exception as e:
            logger.warning(f"[Push] Topic subscription failed for {topic}: {e}")

async def send_breaking_news_push(title: str, article_id: str = "", url: str = "/", topic: str = "breaking_news") -> None:
    """
    Send breaking news push alert to the specified FCM topic (defaults to 'breaking_news').
    """
    if not title:
        return
    try:
        message = messaging.Message(
            notification=messaging.Notification(
                title="UCKhabar",
                body=title
            ),
            data={
                "tag": topic,
                "article_id": str(article_id),
                "url": str(url)
            },
            topic=topic
        )
        response = messaging.send(message)
        logger.info(f"[Push] Sent breaking news broadcast: {response} (body: '{title}')")
    except Exception as e:
        logger.error(f"[Push] Failed to send breaking news push: {e}")

async def send_feed_ready_push(tokens: List[str], time_of_day: str = "curated") -> None:
    """
    Send push notification to a user's tokens when their feed is built/ready.
    time_of_day can be 'morning', 'afternoon', 'evening', or 'curated'.
    """
    if not tokens:
        return
    
    body_text = f"Your {time_of_day} feed is ready. Tap to read today's curated stories."
    if time_of_day == "curated":
        body_text = "Your personalized AI news feed is ready to explore."
    
    messages = []
    for token in tokens:
        messages.append(
            messaging.Message(
                notification=messaging.Notification(
                    title="UCKhabar News Alert",
                    body=body_text
                ),
                data={
                    "tag": "feed-ready",
                    "url": "/"
                },
                token=token
            )
        )
    
    if not messages:
        return

    try:
        # Send up to 500 messages at once
        response = messaging.send_each(messages)
        logger.info(f"[Push] Sent feed ready alerts: {response.success_count} success, {response.failure_count} failed")
    except Exception as e:
        logger.error(f"[Push] Failed to send feed ready push batch: {e}")
