# Mighty Miner

# Installation
1. Download the latest [release](https://github.com/KFung95/Mighty-Miner/releases).
2. Extract it.
3. Run MightyMiner.exe.

# FAQ
> Will I be banned for using this?

To my knowledge, no as the program doesn't interact with the game whatsoever. Just like keyboard and mouse profile programs, this is meant to run in the background. However, use at your own risk.

> My antivirus is flagging this as malicious. Is this safe?

Yes. It's flagging due to the key tracking feature. If you want to make sure this is safe, you can review the source code and build the executable yourself with the instructions below.

# Build
If you would like to build your own executable file using the source code, download the repo, extract, navigate to the extracted directory and run the following:

`pip install -r requirements.txt`

`python -m PyInstaller --noconsole --onefile --uac-admin --name "MightyMiner" PhotonTrackerFinalUIv2.py`

This will create two directories: build and dist

The newly built executable file will be in the build dist directory. Please make sure the image folder and settings.json file are in the same location as the executable.