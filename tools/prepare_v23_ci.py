from pathlib import Path
import runpy
runpy.run_path("tools/prepare_v22.py",run_name="__main__")
for f in ["app/build.gradle","app/src/main/java/com/vk/cy01streamlab/MainActivityV03.java","app/src/main/java/com/vk/cy01streamlab/RawRtspH264Activity.java"]:
 p=Path(f); s=p.read_text()
 s=s.replace("cy01streamlab22","cy01streamlab23").replace("2200","2300").replace("2.2.0","2.3.0").replace("v2.2","v2.3").replace("/2.2","/2.3")
 if f.endswith("RawRtspH264Activity.java"):
  s=s.replace("dequeueInputBuffer(10_000)","dequeueInputBuffer(2_000)")
 p.write_text(s)
print("v2.3 prepared")
