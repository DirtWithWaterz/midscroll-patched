patch for toggle+anchor; unit override / divert

fully install midscroll before following the instructions below.

sudo cp \[path to this repo\]/midscroll.py /usr/bin/midscroll
sudo chmod 755 /usr/bin/midscroll

sudo dpkg-divert --add --rename --divert /usr/bin/midscroll.dist /usr/bin/midscroll

sudo install -m 755 /[path to this repo\]/midscroll-overlay-x11.py /usr/local/bin/midscroll-overlay-x11
mkdir -p ~/.config/systemd/user/midscroll-overlay.service.d
nano ~/.config/systemd/user/midscroll-overlay.service.d/x11.conf

paste this into the nano file (without the parenthesis):
"
[Service]
ExecStart=
ExecStart=/usr/local/bin/midscroll-overlay-x11
"

then save and exit the nano and run the following:

systemctl --user daemon-reload
systemctl --user restart midscroll-overlay

systemctl --user is-enabled midscroll-overlay
