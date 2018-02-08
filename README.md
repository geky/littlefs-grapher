A quick and dirty script for debugging littlefs images by rendering the
filesystem to a web browser.

This script was thrown together hastily and may or may not work. Use at your
own risk!

Only possible because of these projects:
- https://github.com/almende/vis
- https://github.com/nathancahill/Split.js

How to use:
``` bash
# Note! the following must be named data.json
$ ./littlefs-grapher.py image > data.json
$ python -m SimpleHTTPServer 1234
```

Now you can navigate to https://localhost:1234 in a web browser.

You can find an example (with the [littlefs](https://github.com/geky/littlefs)
source tree) on the gh_pages branch:  
https://geky.github.io/littlefs-grapher/graph.html
