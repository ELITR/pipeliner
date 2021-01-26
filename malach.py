from src.pipeliner import Pipeliner

p = Pipeliner(logsDir="/pwd/logs")

audioRecording = p.addLocalNode("audioRecording", {}, {"audiorecord": "stdout"}, "nc -lk 5000")
asr = p.addLocalNode("ASR", 
        {"audio": "stdin"}, 
        {"transcription": "stdout"}, 
        "ebclient -s mediator.pervoice.com -p 4448 -r --timestamps -f en-EU-lecture_KIT-s2s")
segmenter = p.addLocalNode("segmenter", {"ctmASR": "stdin"}, {"segmented": "stdout"}, "python3 /tools/ctm_segmenter.py")
events = p.addLocalNode("events", {"asrOutput": "stdin"}, {"processed": "stdout"}, "online-text-flow events en -b")
chopper = p.addLocalNode("chopper", {"raw": "stdin"}, {"chopped": "stdout"}, "/cruise-control/chopper/subtitler.sh --width=70 --desired-flicker=2 ")

output = p.addLocalNode("output", {"logging": "stdin"}, {}, "cat")

p.addEdge(audioRecording, "audiorecord", asr, "audio")
p.addEdge(asr, "transcription", events, "asrOutput")
p.addEdge(events, "processed", chopper, "raw")
p.addEdge(chopper, "chopped", output, "logging")

p.logging = True
p.createPipeline()