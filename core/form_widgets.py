"""Shared form control attrs — selects, dates, times."""

from django import forms


def select_attrs(*, searchable: bool = False, extra_class: str = "") -> dict:
    classes = ["ui-select"]
    if extra_class:
        classes.append(extra_class)
    attrs = {"class": " ".join(classes)}
    if searchable:
        attrs["data-searchable"] = "1"
        attrs["data-search-placeholder"] = "Search…"
    return attrs


def date_attrs(**extra) -> dict:
    cls = extra.pop("class", "")
    classes = ["ui-date"]
    if cls:
        classes.append(cls)
    return {"type": "date", "class": " ".join(classes), **extra}


def time_attrs(**extra) -> dict:
    return {"type": "time", "class": "ui-time", **extra}


def datetime_attrs(**extra) -> dict:
    return {"type": "datetime-local", "class": "ui-datetime", **extra}


def date_widget(**extra):
    """HTML5 date input with ISO format (fixes empty values on edit)."""
    return forms.DateInput(format="%Y-%m-%d", attrs=date_attrs(**extra))


def time_widget(**extra):
    return forms.TimeInput(format="%H:%M", attrs=time_attrs(**extra))


def datetime_widget(**extra):
    return forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs=datetime_attrs(**extra))
