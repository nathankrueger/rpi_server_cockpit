import psutil

def kill_proc_tree(pid):
    """Terminate a process and all its children recursively."""
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        # Kill children first
        for child in children:
            child.terminate()
        # Kill parent
        parent.terminate()
        
        # Wait for them to actually exit
        _, alive = psutil.wait_procs(children + [parent], timeout=1)
        
        # If any are still alive, force kill them
        for p in alive:
            p.kill()
    except psutil.NoSuchProcess:
        pass
