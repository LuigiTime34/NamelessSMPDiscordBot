def format_playtime(seconds):
    """Format seconds into a readable time string."""
    hours, remainder = divmod(seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    
    result = ""
    if hours > 0:
        result += f"{hours}h "
    result += f"{minutes}m"
    
    return result.strip()

def add_embed_fields(embed, name, content):
    """Split long content into multiple embed fields."""
    chunks = [content[i:i + 1000] for i in range(0, len(content), 1000)]
    for index, chunk in enumerate(chunks):
        embed.add_field(name=f"{name} (Part {index + 1})" if len(chunks) > 1 else name, 
                       value=f"```{chunk}```", inline=False)