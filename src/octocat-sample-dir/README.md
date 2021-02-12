# octocat sample directory

This directory illustrates how to use octocat.

## Usage

Run ``../octocat.py`` from this directory.

Use several terminal windows to run octocat, feed inputs to it, and select the output.

### Window 1: Octocat Itself

Launch octocat here, watch the output from octocat here.

```
../octocat.py
```

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
tail channel-one.preview
  # for a quick peek
tail -f channel-one.preview
  # for continuous preview
```

### Window 5: Selecting

Depending on the previews, use these commands to select one of the channels. Octocat will emit that one until you change your mind.

```
echo channel-one > SELECT
```

