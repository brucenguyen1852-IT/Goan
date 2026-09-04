"""Hằng số cho thông báo đẩy."""

from enum import Enum


class DevicePlatform(str, Enum):
    ANDROID = "android"
    IOS = "ios"
    WEB = "web"
