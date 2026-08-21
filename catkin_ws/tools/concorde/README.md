# Concorde and Linkern

The measured workspace used the University of Waterloo Linux executables:

```text
https://www.math.uwaterloo.ca/tsp/concorde/downloads/codes/linux24/concorde.gz
https://www.math.uwaterloo.ca/tsp/concorde/downloads/codes/linux24/linkern.gz
```

Download and unpack them into this directory, then make them executable:

```bash
gzip -dk concorde.gz
gzip -dk linkern.gz
chmod +x concorde linkern
```

The binaries are excluded from Git because they are platform-specific
third-party redistributables. Their source URLs are also pinned in
`catkin_ws/DEPENDENCIES.lock`.
