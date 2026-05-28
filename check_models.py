import onnxruntime as ort
import openwakeword, os

d = os.path.join(os.path.dirname(openwakeword.__file__), "resources", "models")

for name in ["melspectrogram.onnx", "embedding_model.onnx"]:
    sess = ort.InferenceSession(os.path.join(d, name))
    print(f"\n=== {name} ===")
    for i in sess.get_inputs():
        print(f"  INPUT  {i.name}: {i.shape} {i.type}")
    for o in sess.get_outputs():
        print(f"  OUTPUT {o.name}: {o.shape} {o.type}")