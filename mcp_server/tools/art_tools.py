"""美育相关 MCP 工具

提供艺术鉴赏、作品分析、创作指导等美育教育功能。
"""

from mcp.server import Server
from mcp.types import Tool, TextContent


def register_art_tools(server: Server):
    """注册美育相关的所有工具到 MCP 服务器"""

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """列出所有可用的美育工具"""
        return [
            Tool(
                name="analyze_artwork",
                description="分析艺术作品的特征、风格和技法",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "作品名称"
                        },
                        "description": {
                            "type": "string",
                            "description": "作品描述或特征说明"
                        }
                    },
                    "required": ["title"]
                }
            ),
            Tool(
                name="generate_art_prompt",
                description="根据主题生成艺术创作提示词，辅助美育教学",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "theme": {
                            "type": "string",
                            "description": "创作主题"
                        },
                        "style": {
                            "type": "string",
                            "description": "艺术风格（如油画、水彩、水墨、素描等）",
                            "default": "水彩"
                        },
                        "level": {
                            "type": "string",
                            "enum": ["初级", "中级", "高级"],
                            "description": "难度等级",
                            "default": "初级"
                        }
                    },
                    "required": ["theme"]
                }
            ),
            Tool(
                name="art_knowledge_qa",
                description="回答艺术和美育相关的知识问题",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "艺术相关问题"
                        }
                    },
                    "required": ["question"]
                }
            )
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        """处理工具调用"""
        if name == "analyze_artwork":
            title = arguments.get("title", "")
            desc = arguments.get("description", "无详细描述")
            return [TextContent(
                type="text",
                text=f"作品《{title}》分析\n"
                     f"描述：{desc}\n"
                     f"【分析结果】\n"
                     f"该工具将结合 AI 对作品进行风格定位、技法分析和美学评价。"
            )]

        elif name == "generate_art_prompt":
            theme = arguments.get("theme", "")
            style = arguments.get("style", "水彩")
            level = arguments.get("level", "初级")
            return [TextContent(
                type="text",
                text=f"【{level}·{style}】创作主题：{theme}\n"
                     f"提示词：请以{style}风格表现「{theme}」，"
                     f"适合{level}学习者练习，注重基础技法与创意表达的结合。"
            )]

        elif name == "art_knowledge_qa":
            question = arguments.get("question", "")
            return [TextContent(
                type="text",
                text=f"问题：{question}\n"
                     f"该工具将调用 AI 知识库回答艺术和美育相关问题。"
            )]

        else:
            return [TextContent(
                type="text",
                text=f"未知工具: {name}"
            )]
