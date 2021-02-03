from src.pipeliner import Pipeliner
# To be executed inside a Docker container of a cruise-control image.
# To see the bind mounts, see the docker-compose.yaml file.
# If executing locally, change the paths to executables.

TEXTFLOW = "ws://127.0.0.1:5002/textflow"

p = Pipeliner(logsDir="/pwd/logs")

audioRecording = p.addLocalNode("audioRecording", {}, {"audiorecord": "stdout"}, "nc -lk 5000")
asr = p.addLocalNode("ASR", 
        {"audio": "stdin"}, 
        {"transcription": "stdout"}, 
        "ebclient -s mediator.pervoice.com -p 4448 -r --timestamps -f en-EU-lecture_KIT-S2S -i en-EU -t text")
events = p.addLocalNode("events", {"asrOutput": "stdin"}, {"processed": "stdout"}, "online-text-flow events en -b")
en_online_text_flow = p.addLocalNode("en_online_text_flow", {"sentences": "stdin"}, {}, f"online-text-flow-client en {TEXTFLOW} -b")
KIT_rainbow_mt = p.addLocalNode("KIT_rainbow_mt",
                {"source": "stdin"}, 
                {"targets": "stdout"}, 
                "/cruise-control/mt-wrapper/mt-wrapper.py --mt \"textclient -p 4448 -f en-EU -i rb-EU_fromEN-en_to_41_all\"")

splitter_langs = ["cs", "de"]
splitter_ports = [p.availablePorts.pop() for lang in splitter_langs]
splitter = p.addLocalNode("rainbow_mt_splitter", {"source": "stdin"}, {lp[0]: lp[1] for lp in zip(splitter_langs, splitter_ports)}, f"python3 /src/rainbow_splitter.py {' '.join(splitter_langs)} {' '.join(map(lambda p: str(p), splitter_ports))}")

for lang in splitter_langs:
        flow = p.addLocalNode(f"{lang}_online_text_flow", {"sentences": "stdin"}, {}, f"online-text-flow-client {lang} {TEXTFLOW} -b")
        p.addEdge(splitter, lang, flow, "sentences")

p.addEdge(audioRecording, "audiorecord", asr, "audio")
p.addEdge(asr, "transcription", events, "asrOutput")
p.addEdge(events, "processed", en_online_text_flow, "sentences")

p.addEdge(asr, "transcription", KIT_rainbow_mt, "source")
p.addEdge(KIT_rainbow_mt, "targets", splitter, "source")

p.logging = True
p.createPipeline()