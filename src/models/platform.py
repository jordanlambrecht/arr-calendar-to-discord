#!/usr/bin/env python3
# src/models/platform.py

import re
from abc import ABC, abstractmethod
from typing import Dict, List, Any
from datetime import datetime
import logging

from models.day import Day
from models.event_item import EventItem
from config.settings import Config
from utils.format_utils import (
    format_header_text, format_subheader_text, get_day_colors,
    format_timezone_line # Import the new function
)
from constants import (
    PLATFORM_DISCORD,
    PLATFORM_SLACK,
    EPISODE_PATTERN,
    # Import styling constants needed here
    DISCORD_BOLD_START, DISCORD_BOLD_END, DISCORD_ITALIC_START, DISCORD_ITALIC_END, DISCORD_STRIKE_START, DISCORD_STRIKE_END,
    SLACK_BOLD_START, SLACK_BOLD_END, SLACK_ITALIC_START, SLACK_ITALIC_END, SLACK_STRIKE_START, SLACK_STRIKE_END,
    ITALIC_START, ITALIC_END # Universal italic
)
from services.webhook_service import WebhookService

# Regex to identify common SxxExx or NNNxNNN patterns (case-insensitive)
# Allows S prefix, 1-4 digits for season, E or x separator, 1-4 digits for episode
EPISODE_PATTERN = re.compile(EPISODE_PATTERN, re.IGNORECASE)

logger = logging.getLogger("service_platform")


class Platform(ABC):
    """Abstract base class for messaging platforms"""
    
    def __init__(self, webhook_url: str, webhook_service: WebhookService, success_codes: List[int], config: Config  ):
        """
        Initialize platform
        
        Args:
            webhook_url: URL to send messages to
            webhook_service: Service for sending webhook requests
            success_codes: HTTP status codes that indicate success
            config: Application configuration
        """
        self.webhook_url = webhook_url
        self.webhook_service = webhook_service
        self.success_codes = success_codes
        self.config = config
        self.day_colors = self._initialize_day_colors()
    
    @abstractmethod
    def _initialize_day_colors(self) -> Dict[str, Any]:
        """
        Initialize color scheme for days
        
        Returns:
            Dictionary mapping day names to colors
        """
        pass
    
    @abstractmethod
    def format_day(self, day: Day) -> Dict[str, Any]:
        """
        Format a day for this platform
        
        Args:
            day: Day to format
            
        Returns:
            Platform-specific day representation
        """
        pass
    
    @abstractmethod
    def format_header(self, custom_header: str, start_date: datetime, 
                     end_date: datetime, show_date_range: bool,
                     tv_count: int, movie_count: int, premiere_count: int) -> Dict[str, Any]:
        """
        Format header for this platform
        
        Args:
            custom_header: Header text
            start_date: Start date
            end_date: End date
            show_date_range: Whether to show date range
            tv_count: Number of TV episodes
            movie_count: Number of movie releases
            premiere_count: Number of premieres
            
        Returns:
            Platform-specific header representation
        """
        pass
    
    def send_message(self, payload: Dict[str, Any]) -> bool:
        """
        Send message to platform
        
        Args:
            payload: Data to send
            
        Returns:
            Whether message was sent successfully
        """
        return self.webhook_service.send_request(
            self.webhook_url,
            payload,
            self.success_codes
        )
    
    @abstractmethod
    def format_tv_event(self, event_item: EventItem, passed_event_handling: str) -> str:
        """
        Format a TV event for this platform
        
        Args:
            event_item: EventItem to format
            passed_event_handling: How to handle passed events (DISPLAY, HIDE, STRIKE)
            
        Returns:
            Formatted string for this platform
        """
        pass
    
    @abstractmethod
    def format_movie_event(self, event_item: EventItem, passed_event_handling: str) -> str:
        """
        Format a movie event for this platform
        
        Args:
            event_item: EventItem to format
            passed_event_handling: How to handle passed events (DISPLAY, HIDE, STRIKE)
            
        Returns:
            Formatted string for this platform
        """
        pass


class  DiscordPlatform(Platform):
    """Discord implementation of Platform"""
    
    def __init__(self, webhook_url: str, webhook_service: WebhookService, 
                 success_codes: List[int], config: Config):
        """Initialize with configuration"""
        super().__init__(webhook_url, webhook_service, success_codes, config)

        
    def _initialize_day_colors(self) -> Dict[str, int]:
        """
        Initialize color scheme for days
        
        Returns:
            Dictionary mapping day names to Discord color integers
        """
        return get_day_colors(PLATFORM_DISCORD, self.config.start_week_on_monday)
    
    def format_day(self, day: Day) -> Dict[str, Any]:
        """
        Format a day as Discord embed
        
        Args:
            day: Day to format
            
        Returns:
            Discord embed object
        """
        # Get color for this day
        color = self.day_colors.get(day.day_name, 0)
        
        # Format TV and movie events
        tv_formatted = [
            self.format_tv_event(event, self.config.passed_event_handling) 
            for event in day.tv_events
        ]
        
        movie_formatted = [
            self.format_movie_event(event, self.config.passed_event_handling) 
            for event in day.movie_events
        ]
        
        # Combine tv and movie listings
        description = ""
        if tv_formatted:
            description += "\n".join(tv_formatted)
            if movie_formatted:
                description += "\n\n"
        
        if movie_formatted:
            description += "**MOVIES**\n" + "\n".join(movie_formatted)
        
        return {
            "title": day.name,
            "description": description,
            "color": color
        }
    
    def format_header(self, custom_header: str, start_date: datetime, 
                     end_date: datetime, show_date_range: bool,
                     tv_count: int, movie_count: int, premiere_count: int) -> Dict[str, Any]:
        """
        Format Discord header message
        
        Args:
            custom_header: Header text
            start_date: Start date
            end_date: End date
            show_date_range: Whether to show date range
            tv_count: Number of TV episodes
            movie_count: Number of movie releases
            premiere_count: Number of premieres
            
        Returns:
            Discord message object
        """
        # Create header with formatted date
        header_text = format_header_text(custom_header, start_date, end_date, show_date_range)
        subheader = format_subheader_text(tv_count, movie_count, premiere_count, PLATFORM_DISCORD)

        # --- Get Timezone Line if needed ---
        timezone_line = ""
        if self.config.show_timezone_in_subheader:
            # Call the utility function
            timezone_line = format_timezone_line(self.config.timezone_obj, PLATFORM_DISCORD)
        # --- End Timezone Line ---

        # --- Create Mention Text ---
        mention_text = ""
        role_id = self.config.discord_mention_role_id
        hide_instructions = self.config.discord_hide_mention_instructions

        logger.debug(f"Discord mention check: Role ID='{role_id}', Hide Instructions='{hide_instructions}' (Type: {type(hide_instructions)})")

        if role_id: # Check if role_id is not None and not empty
            # REMOVE leading \n from the mention itself
            mention_text = f"<@&{role_id}>"
            if not hide_instructions:
                # Keep the \n between the mention and the instructions
                mention_text += f"\n{ITALIC_START}If you'd like to be notified when new content is available, join this role!{ITALIC_END}"

        # Combine parts: Header, Subheader, Timezone Line (if any), Mention Text (if any)
        if timezone_line:
            final_content += f"\n\n{timezone_line}"
        if mention_text:
            final_content += f"\n\n{mention_text}" 

        return {
            "content": final_content
        }
    
    def format_tv_event(self, event_item: EventItem, passed_event_handling: str) -> str:
        """
        Format a TV event

        Args:
            event_item: EventItem to format
            passed_event_handling: How to handle passed events (DISPLAY, HIDE, STRIKE)
        """
        time_prefix = f"{event_item.time_str}: " if event_item.time_str else ""
        show_name_to_format = event_item.show_name if event_item.show_name else event_item.summary

        formatted_show = f"{DISCORD_BOLD_START}{show_name_to_format}{DISCORD_BOLD_END}"

        episode_details = ""
        number = event_item.episode_number
        title = event_item.episode_title

        if title:
            is_standard_ep_num = bool(number and EPISODE_PATTERN.match(number))
            if is_standard_ep_num:
                episode_details = f" - {number} - {DISCORD_ITALIC_START}{title}{DISCORD_ITALIC_END}"
            else:
                episode_details = f" - {DISCORD_ITALIC_START}{number} - {title}{DISCORD_ITALIC_END}"
        elif number:
            is_standard_ep_num = bool(EPISODE_PATTERN.match(number))
            if is_standard_ep_num:
                # Standard number only: Show - SxxExx
                episode_details = f" - {number}"
            else:
                # Non-standard number only: Show - *Number*
                episode_details = f" - {DISCORD_ITALIC_START}{number}{DISCORD_ITALIC_END}"

        formatted = f"{time_prefix}{formatted_show}{episode_details}"
        if event_item.is_premiere:
            formatted += " 🎉"
        if event_item.is_past and passed_event_handling == "STRIKE":
            formatted = f"{DISCORD_STRIKE_START}{formatted}{DISCORD_STRIKE_END}"

        return formatted.strip()
    
    def format_movie_event(self, event_item: EventItem, passed_event_handling: str) -> str:
        """Format a movie event for Discord"""
        time_prefix = f"{event_item.time_str}: " if event_item.time_str else ""
        movie_name_to_format = event_item.show_name if event_item.show_name else event_item.summary
        # Use Discord bold constants
        formatted = f"{time_prefix}{DISCORD_BOLD_START}{movie_name_to_format}{DISCORD_BOLD_END}"

        if event_item.is_past and passed_event_handling == "STRIKE":
            formatted = f"{DISCORD_STRIKE_START}{formatted}{DISCORD_STRIKE_END}"

        return formatted.strip()


class SlackPlatform(Platform):
    """Slack implementation of Platform"""
    
    def __init__(self, webhook_url: str, webhook_service: WebhookService, 
                 success_codes: List[int], config: Config):
        """Initialize with configuration"""
        super().__init__(webhook_url, webhook_service, success_codes, config)
        # self.config = config
    
    def _initialize_day_colors(self) -> Dict[str, str]:
        """
        Initialize color scheme for days
        
        Returns:
            Dictionary mapping day names to Slack color hex strings
        """
        return get_day_colors(PLATFORM_SLACK, self.config.start_week_on_monday)
    
    def format_day(self, day: Day) -> Dict[str, Any]:
        """
        Format a day as Slack attachment
        
        Args:
            day: Day to format
            
        Returns:
            Slack attachment object
        """
        # Get color for this day
        color = self.day_colors.get(day.day_name, "#000000")
        
        # Format TV and movie events
        tv_formatted = [
            self.format_tv_event(event, self.config.passed_event_handling) 
            for event in day.tv_events
        ]
        
        movie_formatted = [
            self.format_movie_event(event, self.config.passed_event_handling) 
            for event in day.movie_events
        ]
        
        # Combine tv and movie listings
        text = ""
        if tv_formatted:
            text += "\n".join(tv_formatted)
            if movie_formatted:
                text += "\n\n"
        
        if movie_formatted:
            text += "*MOVIES*\n" + "\n".join(movie_formatted)
        
        return {
            "color": color,
            "title": day.name,
            "text": text,
            "mrkdwn_in": ["text"]
        }
    
    def format_header(self, custom_header: str, start_date: datetime, 
                     end_date: datetime, show_date_range: bool,
                     tv_count: int, movie_count: int, premiere_count: int) -> Dict[str, Any]:
        """
        Format Slack header message
        
        Args:
            custom_header: Header text
            start_date: Start date
            end_date: End date
            show_date_range: Whether to show date range
            tv_count: Number of TV episodes
            movie_count: Number of movie releases
            premiere_count: Number of premieres
            
        Returns:
            Slack message object with blocks
        """
        # Create header text and date range text
        header_text = format_header_text(custom_header, start_date, end_date, show_date_range)
        date_range_text = "" # Slack doesn't use the date range in the main text block

        # Create subheader text (without timezone)
        subheader_text = format_subheader_text(tv_count, movie_count, premiere_count, PLATFORM_SLACK).strip() # Remove trailing newlines

        #Get timezone line if needed
        timezone_line = ""
        if self.config.show_timezone_in_subheader:
            # Call the utility function
            timezone_line = format_timezone_line(self.config.timezone_obj, PLATFORM_SLACK)

        # Combine parts for the main text block
        message_text = f"{header_text}\n\n{subheader_text}{timezone_line}"

        # Return Slack block payload
        return {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": message_text
                    }
                }
            ]
        }
    
    def format_tv_event(self, event_item: EventItem, passed_event_handling: str) -> str:
        """
        Format a TV event for Slack, applying italics based on content.
        """
        time_prefix = f"{event_item.time_str}: " if event_item.time_str else ""
        show_name_to_format = event_item.show_name if event_item.show_name else event_item.summary
        formatted_show = f"{SLACK_BOLD_START}{show_name_to_format}{SLACK_BOLD_END}"

        episode_details = ""
        number = event_item.episode_number
        title = event_item.episode_title

        if title:
            is_standard_ep_num = bool(number and EPISODE_PATTERN.match(number))
            if is_standard_ep_num:
                episode_details = f" - {number} - {SLACK_ITALIC_START}{title}{SLACK_ITALIC_END}"
            else:
                episode_details = f" - {SLACK_ITALIC_START}{number} - {title}{SLACK_ITALIC_END}"
        elif number:
            is_standard_ep_num = bool(EPISODE_PATTERN.match(number))
            if is_standard_ep_num:
                episode_details = f" - {number}"
            else:
                episode_details = f" - {SLACK_ITALIC_START}{number}{SLACK_ITALIC_END}"

        formatted = f"{time_prefix}{formatted_show}{episode_details}"
        if event_item.is_premiere:
            formatted += " 🎉"
        if event_item.is_past and passed_event_handling == "STRIKE":
            formatted = f"{SLACK_STRIKE_START}{formatted}{SLACK_STRIKE_END}"

        return formatted.strip()
    
    def format_movie_event(self, event_item: EventItem, passed_event_handling: str) -> str:
        """Format a movie event for Slack"""
        time_prefix = f"{event_item.time_str}: " if event_item.time_str else ""
        movie_name_to_format = event_item.show_name if event_item.show_name else event_item.summary
        formatted = f"{time_prefix}{SLACK_BOLD_START}{movie_name_to_format}{SLACK_BOLD_END}"

        if event_item.is_past and passed_event_handling == "STRIKE":
            formatted = f"{SLACK_STRIKE_START}{formatted}{SLACK_STRIKE_END}"

        return formatted.strip()