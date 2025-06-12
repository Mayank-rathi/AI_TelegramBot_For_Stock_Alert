# Chartink Stock Scanner Bot

A Telegram bot that scans Chartink for stock signals based on custom criteria and sends notifications.

## Features

- Automated stock scanning during market hours (9:15 AM to 3:15 PM IST)
- Customizable scanning criteria
- Telegram notifications with detailed stock information
- Robust error handling and retry mechanisms
- Process management to prevent multiple instances
- Configurable scanning intervals

## Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd <repository-directory>
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure the bot:
   - Edit `config.py` to set your Telegram bot token and chat ID
   - Adjust trading hours and scanning intervals if needed
   - Modify the scanning criteria in `SCAN_CLAUSE` if required

4. Run the bot:
```bash
python SniperScannerChartink.py
```

## Configuration

The bot can be configured by editing `config.py`:

- `BOT_TOKEN`: Your Telegram bot token
- `CHAT_ID`: Your Telegram chat ID
- `TRADING_START_HOUR`: Market opening hour (default: 9)
- `TRADING_START_MINUTE`: Market opening minute (default: 15)
- `TRADING_END_HOUR`: Market closing hour (default: 15)
- `TRADING_END_MINUTE`: Market closing minute (default: 15)
- `SCAN_INTERVAL_MINUTES`: Interval between scans (default: 15)

## Usage

1. Start the bot during market hours
2. The bot will automatically:
   - Scan for stocks matching the criteria
   - Send notifications to your Telegram chat
   - Handle weekends and non-trading hours
   - Retry on failures

## Logging

Logs are written to `chartink_bot.log` and also displayed in the console. The log file contains:
- Scan results
- Error messages
- Bot status updates

## Error Handling

The bot includes:
- Automatic retries for API calls
- Process management to prevent multiple instances
- Graceful shutdown on termination signals
- Weekend and non-trading hour handling

## Contributing

Feel free to submit issues and enhancement requests! 