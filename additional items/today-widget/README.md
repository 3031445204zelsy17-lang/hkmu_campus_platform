# Today at HKMU Widget Prototype

This folder saves the idea and code for a standalone homepage widget.

## Purpose

The widget is designed for the top-left area of the homepage. It uses a vertical
3:4 layout and rotates through:

- School news
- Personal schedule, including classes, exams, and custom events
- Club reminders and group activities

## Files

- `index.html` - standalone demo page
- `today-widget.css` - widget styles
- `today-widget.js` - slide rotation logic

## Future integration

When this prototype is added to the real homepage, it can connect to:

- News API
- Course and exam schedule API
- Custom activity API
- Group and event API

Suggested backend endpoint:

```text
GET /api/v1/dashboard/today
```

The response can combine the most important items for the current student.
