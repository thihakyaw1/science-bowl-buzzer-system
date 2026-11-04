Science Bowl Buzzer System! - Thiha Kyaw, Venice High School Class of 2027

Install Python 3.11 or newer. Download and extract this repository, then open a terminal in the folder containing `run_app.py`.

Run:

```bash
cd "Science Bowl Buzzer Project"
python run_app.py
```
Open http://127.0.0.1:8080 in your browser.

And that's it! Have fun!

For this demo version, Use the dashboard’s player buttons to simulate buzzes. Games save locally in the `data` folder.

Press Ctrl+C in the terminal to stop the app.

Keyboard controls:
T = start five-second timer
C = correct
W = incorrect
U = undo
D = delete/reset
N = new round
Shortcuts are disabled while typing in a field.









FEATURES: (not for demo, if you actually want to use my code along with Raspberry Pi and my setups) (discord message me _thihaa if you want to see my MCP23017, reset circuit and my overall hardware I'd say)

Install the application dependencies for PDF import, hardware access, and Google integration:

```bash
python -m pip install -r requirements.txt
```

For Google setup, see `scripts/google/SETUP.md`. Internet access is required for Google syncing and downloading question PDFs.

Run with Raspberry Pi hardware

Enable I2C and install the dependencies first. For this build’s MCP23017 address and verified isolated reset circuit:

```bash
python run_app.py --host 0.0.0.0 --mcp23017 --mcp-address 0x27 --reset-gpio 18 --reset-pulse-ms 1000
```

Open `http://<PI-IP-ADDRESS>:8080` from a connected laptop.

If the reset relay is not connected, remove `--reset-gpio 18 --reset-pulse-ms 1000` and use the physical reset button.





BOOM Thank you for reading my README!
