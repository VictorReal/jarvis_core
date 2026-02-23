import edge_tts
import os
import asyncio
import subprocess
import time

def speak(text):
   
    clean_text = text.replace("*", "").replace("#", "").strip()
    
    if not clean_text:
        return

    asyncio.run(_generate_and_play(clean_text))

async def _generate_and_play(text):
    voice = "en-GB-RyanNeural" 
    filename = os.path.abspath("voice_temp.mp3")
    
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(filename)

        
        powershell_command = (
            f"$player = New-Object System.Media.SoundPlayer; "
            f"$m = New-Object Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager; " 
            f"Add-Type -AssemblyName presentationCore; "
            f"$mediaPlayer = New-Object System.Windows.Media.MediaPlayer; "
            f"$mediaPlayer.Open('{filename}'); "
            f"$mediaPlayer.Play(); "
            f"Start-Sleep -s {(len(text) // 15) + 2}" 
        )
        
        subprocess.run(["powershell", "-Command", powershell_command], capture_output=True)

        if os.path.exists(filename):
            os.remove(filename)
            
    except Exception as e:
        print(f"JARVIS Voice Error: {e}")
    