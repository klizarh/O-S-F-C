#!/bin/bash

DATE=$(date +"%Y-%m-%d_%H%M")

#fswebcam -r 1280x720 --no-banner /home/pi/MVP/pictures/$DATE.jpg

fswebcam -r 1280x720 --title Sammies_MARSfarm /home/pi/MVP/pictures/$DATE.jpg