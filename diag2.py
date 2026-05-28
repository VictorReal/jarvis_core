import onnxruntime as ort, librosa, numpy as np, openwakeword, os

SAMPLE_RATE = 16000
MEL_CHUNK   = 1280

d = os.path.join(os.path.dirname(openwakeword.__file__), "resources", "models")
mel_sess = ort.InferenceSession(os.path.join(d, "melspectrogram.onnx"))

audio, _ = librosa.load("wake_words/training/ultron/ultron_0001.wav", sr=SAMPLE_RATE, mono=True)
audio = audio.astype(np.float32)

# один чанк
chunk = audio[:MEL_CHUNK].reshape(1, -1)
mel_out = mel_sess.run(None, {"input": chunk})[0]
print("mel_out.shape:", mel_out.shape)
print("mel_out dtype:", mel_out.dtype)

# три чанки
chunk3 = audio[:MEL_CHUNK*3].reshape(1, -1)
mel_out3 = mel_sess.run(None, {"input": chunk3})[0]
print("mel_out3.shape (3 chunks):", mel_out3.shape)