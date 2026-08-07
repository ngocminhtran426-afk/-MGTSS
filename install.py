import os
import sys
import subprocess
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from InquirerPy import prompt

console = Console()

def check_nvidia_gpu():
    """Check if NVIDIA GPU and CUDA are available."""
    has_gpu = False
    cuda_version = None
    try:
        import pynvml
        pynvml.nvmlInit()
        device_count = pynvml.nvmlDeviceGetCount()
        if device_count > 0:
            has_gpu = True
            cuda_version = pynvml.nvmlSystemGetDriverVersion()
        pynvml.nvmlShutdown()
    except Exception:
        # Fallback to nvidia-smi if pynvml fails or not installed
        try:
            output = subprocess.check_output(["nvidia-smi"]).decode("utf-8")
            if "NVIDIA-SMI" in output:
                has_gpu = True
                # Simple parsing for cuda version could be added here
        except Exception:
            pass
    return has_gpu, cuda_version

def install_pytorch(has_gpu):
    console.print("[bold cyan]Installing PyTorch...[/bold cyan]")
    if has_gpu:
        console.print("[green]NVIDIA GPU detected. Installing PyTorch with CUDA support...[/green]")
        # Example CUDA 11.8 installation for PyTorch
        cmd = [sys.executable, "-m", "pip", "install", "torch", "torchvision", "torchaudio", "--index-url", "https://download.pytorch.org/whl/cu118"]
    else:
        console.print("[yellow]No NVIDIA GPU detected or MacOS/Linux. Installing PyTorch CPU version...[/yellow]")
        cmd = [sys.executable, "-m", "pip", "install", "torch", "torchvision", "torchaudio"]
    subprocess.check_call(cmd)

def check_ffmpeg():
    console.print("[bold cyan]Checking ffmpeg...[/bold cyan]")
    try:
        subprocess.check_output(["ffmpeg", "-version"])
        console.print("[green]ffmpeg is already installed.[/green]")
    except Exception:
        console.print(Panel(Text(
            "ffmpeg is NOT installed or not in PATH.\n"
            "Please install it manually based on your OS:\n"
            "- Windows: choco install ffmpeg\n"
            "- macOS: brew install ffmpeg\n"
            "- Ubuntu/Debian: sudo apt install ffmpeg", 
            style="bold red"
        )))

def install_requirements():
    console.print("[bold cyan]Installing requirements from requirements.txt...[/bold cyan]")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

def main():
    console.print(Panel.fit("Welcome to VideoLingo Installer", style="bold magenta"))
    
    questions = [
        {
            "type": "confirm",
            "message": "Do you want to proceed with the installation?",
            "name": "proceed",
            "default": True,
        }
    ]
    result = prompt(questions)
    
    if not result["proceed"]:
        console.print("[yellow]Installation aborted.[/yellow]")
        return
        
    check_ffmpeg()
    
    # Try importing pynvml, if missing install it temporarily to check hardware
    try:
        import pynvml
    except ImportError:
        console.print("[cyan]Installing pynvml for hardware check...[/cyan]")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pynvml"])
        
    has_gpu, cuda_version = check_nvidia_gpu()
    install_pytorch(has_gpu)
    
    install_requirements()
    console.print("[bold green]Installation completed successfully![/bold green]")

if __name__ == "__main__":
    main()
