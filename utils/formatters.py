def format_playtime(seconds):
    """Format seconds into a readable time string."""
    hours, remainder = divmod(seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    
    result = ""
    if hours > 0:
        result += f"{hours}h "
    result += f"{minutes}m"
    
    return result.strip()