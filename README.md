patch for toggle+anchor; unit override / divert

sudo cp /home/atticus/midscroll/midscroll.py /usr/bin/midscroll
sudo chmod 755 /usr/bin/midscroll

sudo dpkg-divert --add --rename --divert /usr/bin/midscroll.dist /usr/bin/midscroll

