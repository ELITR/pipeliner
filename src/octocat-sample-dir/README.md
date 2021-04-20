# octocat sample directory

This directory illustrates how to use octocat.

## Usage

Use several terminal windows to run octocat, feed inputs to it, and select the output.

### Window 1: Octocat Itself

Launch octocat here, watch the output from octocat here. This will create a directory named `example-dir` which contains the files for output and control. The default input emitted is the first one specified (so 5000 in this example).

```
../octocat.py example-dir 5000 5001
```

Use the `--debug` flag if you want more verbose output or for troubleshooting.

### Window 2: Source One

In this window, you will feed octocat's first input channel, port 5000:

```
nc localhost 5000
# now type whatever you like to send to octocat's input one
```

### Window 3: Source Two

In this window, you will feed octocat's second input channel, port 5001:

```
nc localhost 5001
# now type whatever you like to send to octocat's input two
```

### Window 4: Monitoring

In this window, you can see what octocat is receiving on all its inputs:

```
tail example-dir/5000.preview
  # for a quick peek
tail -f example-dir/5000.preview
  # for continuous preview
```

### Window 5: Selecting

Depending on the previews, use these commands to select one of the channels. Octocat will emit that one until you change your mind. Octocat expects the number of port (that is going to be emitted) in the file. 

```
echo 5001 > SELECT
```

