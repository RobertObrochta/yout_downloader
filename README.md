# yout_downloader
## What it does

## Set Up

## Deployment
### Creating an executable
I recommend using PyInstaller to create a portable executable: ```python -m PyInstaller --onedir .\yout_downloader.py```. In the ```./dist``` directory is the executable, which is where ```config.yaml``` should be placed. This is also the same location that ```app.log``` will appear once the application successfully starts.

### Limitations
Folders should not be named using ```.``` (or ```/``` or ```\``` for that matter). Current behavior is that the application will open Tor and its related Firefox window, then crashes with no error message logged. If it proves to be an issue down the road, I may address this bug.

## Tasklist
- [ ] refactor (all)
- [ ] Add upper and lower limits to download_limit as 3 and 1 respectively
