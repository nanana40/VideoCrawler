"""
口语表达知识库

为常见英语口语表达提供多维度深度分析，包括：
- 中英表达差异
- 语气辨析
- 学习踩坑经验
- 场景拓展
- 语法理解

这些分析模拟人类学习者的真实思考过程，使文案更具个人色彩。
"""

from typing import Dict, List, Optional, Any


class ExpressionKnowledgeBase:
    """
    口语表达知识库
    
    提供常见英语口语表达的深度分析数据。
    """
    
    def __init__(self) -> None:
        """初始化知识库"""
        self._knowledge = self._build_knowledge()
    
    def get_analysis(self, expression: str) -> Optional[Dict[str, str]]:
        """
        获取表达的深度分析
        
        Args:
            expression: 口语表达（小写）
            
        Returns:
            分析数据，如果不存在则返回None
        """
        return self._knowledge.get(expression.lower())
    
    def has_expression(self, expression: str) -> bool:
        """
        检查知识库中是否包含该表达
        
        Args:
            expression: 口语表达
            
        Returns:
            是否存在
        """
        return expression.lower() in self._knowledge
    
    def _build_knowledge(self) -> Dict[str, Dict[str, str]]:
        """构建知识库"""
        return {
            "alright": {
                "meaning": "好吧；好的；没问题",
                "chinese_difference": "中文里我们常说'好吧'来表示勉强同意或接受，'alright'在英语口语中用途更广，既可以表示同意，也可以作为过渡词开启话题。",
                "tone_analysis": "alright 的语气比 ok 稍显随意和口语化，带有一种'那就这样吧'的轻松感。和 okay 相比，alright 更常用于日常闲聊的承接，而 ok 更正式一些。",
                "learning_pitfall": "以前我总是用 ok 来回应一切，但看了这个视频才发现，native speaker 在非正式场合更喜欢用 alright，听起来更自然。",
                "scene_expansion": "适合在朋友聊天、日常对话中使用，比如'Alright, let's get started!'（好吧，我们开始吧！）或者作为开场白'Alright, so...'（好的，那么...）。",
                "grammar_note": "作为感叹词使用，不需要遵循严格的语法规则，常用于句首或句尾。",
            },
            "cool": {
                "meaning": "酷；很棒；有意思",
                "chinese_difference": "中文说'酷'是从英语借来的，但英语中的 cool 用法更广泛，可以形容人、事、物，甚至用来表示'理解了'、'没问题'。",
                "tone_analysis": "cool 的语气非常轻松随意，带有年轻人的活力感。和 great 相比，cool 更口语化，great 稍显正式。",
                "learning_pitfall": "以前我只会说 very good 或者 great，后来发现 cool 在口语中使用频率超高，而且能表达多种情绪，从赞赏到认同都可以用。",
                "scene_expansion": "适合朋友间聊天、社交媒体、日常交流，比如'That's cool!'（太棒了！）或者'Cool, let's do it!'（好的，我们来做吧！）。",
                "grammar_note": "作为形容词使用，也可以单独作为感叹词，口语中经常单独使用一个词表达完整意思。",
            },
            "guys": {
                "meaning": "伙计们；大家；人们",
                "chinese_difference": "中文里很少用一个词统称一群人，我们会说'大家'、'朋友们'，而英语中的 guys 是非常高频的集体称呼，不分性别都可以用。",
                "tone_analysis": "guys 带有友好、随意的语气，适合非正式场合。如果用在正式场合或对长辈，最好用 everyone 或 folks。",
                "learning_pitfall": "以前我以为 guys 只能称呼男生，后来才知道在英语口语中，guys 是一个中性词，女生之间也可以互相称呼 guys。",
                "scene_expansion": "适合朋友聚会、团队讨论、日常聊天，比如'Hey guys!'（嗨，大家好！）或者'Thanks, guys!'（谢谢大家！）。",
                "grammar_note": "虽然看起来是复数形式，但在口语中常作为单数概念使用，指一个群体。",
            },
            "pretty much": {
                "meaning": "差不多；基本上；几乎",
                "chinese_difference": "中文说'差不多'或'基本上'，英语中的 pretty much 更口语化，带有一种随意的总结意味。",
                "tone_analysis": "pretty much 的语气非常口语化，带有一种'就这样了'的总结感。和 almost 相比，pretty much 更强调'已经完成'或'大体如此'。",
                "learning_pitfall": "以前我只会用 almost，后来发现 pretty much 在口语中更常用，而且更自然。特别是在对话结尾总结时，用 pretty much 非常地道。",
                "scene_expansion": "适合对话结尾总结、日常闲聊，比如'And that's pretty much all.'（差不多就是这些了。）或者'Pretty much done!'（差不多完成了！）。",
                "grammar_note": "作为副词短语使用，可以修饰形容词、动词或整个句子，位置比较灵活。",
            },
            "really": {
                "meaning": "非常；真的；确实",
                "chinese_difference": "中文说'非常'、'真的'，英语中的 really 在口语中使用频率极高，而且经常重复使用来加强语气。",
                "tone_analysis": "really 的语气非常强烈，带有真诚和强调的意味。重复使用 really, really, really 可以大大加强语气，表达程度很深。",
                "learning_pitfall": "以前我只会用 very 来表示程度，后来发现 native speaker 在口语中更喜欢用 really，而且经常重复使用，比如'really, really good'听起来比'very good'自然得多。",
                "scene_expansion": "适合日常对话、表达感受、强调程度，比如'That was really fun!'（那真的很有趣！）或者'I really, really like it!'（我非常非常喜欢它！）。",
                "grammar_note": "作为副词使用，可以修饰形容词、副词或动词，位置灵活。",
            },
            "so": {
                "meaning": "那么；所以；非常",
                "chinese_difference": "中文里'那么'更多用于承接，'非常'是程度副词，而英语中的 so 兼具这两种功能，用法非常灵活。",
                "tone_analysis": "so 作为过渡词时语气轻松，作为程度副词时语气强烈。和 very 相比，so 更口语化，表达情感更直接。",
                "learning_pitfall": "以前我只会用 so 来连接句子，后来才发现它还可以作为程度副词，比如'so cool'、'so good'，听起来比'very cool'、'very good'更自然。",
                "scene_expansion": "适合日常对话、表达情感、承接话题，比如'So, what's up?'（那么，最近怎么样？）或者'It's so beautiful!'（太美了！）。",
                "grammar_note": "作为连词时连接两个句子，作为副词时修饰形容词或副词。",
            },
            "well": {
                "meaning": "好吧；嗯；那么",
                "chinese_difference": "中文里'嗯'、'好吧'是语气词，英语中的 well 用法类似，但更常用于正式或半正式场合的开场白。",
                "tone_analysis": "well 的语气带有一种思考、犹豫或勉强同意的感觉。和 alright 相比，well 稍显正式一些。",
                "learning_pitfall": "以前我不知道 well 可以作为开场白，后来发现 native speaker 在思考时经常用 well 开头，比如'Well, I think...'（嗯，我觉得...）。",
                "scene_expansion": "适合思考时的开场白、勉强同意、转移话题，比如'Well, okay then.'（好吧。）或者'Well, let's see.'（嗯，让我想想。）。",
                "grammar_note": "作为感叹词使用，通常放在句首，不需要遵循严格的语法规则。",
            },
            "yeah": {
                "meaning": "是的；好的",
                "chinese_difference": "中文说'是的'、'好的'，英语中的 yeah 更口语化，带有一种随意的同意感。",
                "tone_analysis": "yeah 的语气非常随意轻松，适合非正式场合。和 yes 相比，yeah 更口语化，yes 更正式。",
                "learning_pitfall": "以前我总是用 yes 来回答问题，后来发现朋友聊天时用 yeah 更自然，特别是在日常对话中。",
                "scene_expansion": "适合朋友聊天、日常对话，比如'Yeah, I agree.'（是的，我同意。）或者'Yeah, sure!'（好的，没问题！）。",
                "grammar_note": "作为感叹词使用，单独成句或作为句子的一部分。",
            },
            "kind of": {
                "meaning": "有点；稍微；大概",
                "chinese_difference": "中文说'有点'、'稍微'，英语中的 kind of 更口语化，带有一种不确定或委婉的语气。",
                "tone_analysis": "kind of 的语气委婉，带有一种不确定或保留的意味。和 a little 相比，kind of 更口语化，表达的程度也更模糊。",
                "learning_pitfall": "以前我只会用 a little，后来发现 kind of 在口语中更常用，而且能表达一种模糊的程度，比如'kind of cool'（有点酷）、'kind of tired'（有点累）。",
                "scene_expansion": "适合日常对话、表达不确定的感受，比如'It's kind of interesting.'（有点有趣。）或者'I kind of like it.'（我有点喜欢它。）。",
                "grammar_note": "作为副词短语使用，修饰形容词、副词或动词，位置灵活。",
            },
            "sort of": {
                "meaning": "有点；稍微；大概",
                "chinese_difference": "和 kind of 类似，中文说'有点'、'稍微'，sort of 在英式英语中更常用。",
                "tone_analysis": "sort of 的语气和 kind of 非常相似，都带有委婉和不确定的意味。sort of 在英式英语中更常见，kind of 在美式英语中更常见。",
                "learning_pitfall": "以前我分不清 kind of 和 sort of 的区别，后来发现它们基本可以互换，只是地域偏好不同。",
                "scene_expansion": "适合日常对话、表达不确定的感受，和 kind of 用法完全相同。",
                "grammar_note": "和 kind of 用法相同，作为副词短语使用。",
            },
            "you know": {
                "meaning": "你知道的；对吧；嗯",
                "chinese_difference": "中文里没有完全对应的表达，我们会说'对吧'、'你懂的'，但英语中的 you know 使用频率极高，几乎每句话都可以加。",
                "tone_analysis": "you know 的语气非常口语化，带有一种寻求认同或解释的意味。它不是真的在问对方知不知道，而是一种习惯性的填充词。",
                "learning_pitfall": "以前我不知道 you know 可以作为填充词，后来发现 native speaker 在说话时经常用 you know 来停顿或寻求认同，这是非常地道的口语习惯。",
                "scene_expansion": "适合日常对话、表达观点、寻求认同，比如'It's really important, you know?'（这真的很重要，你知道吗？）或者'You know what I mean?'（你懂我的意思吧？）。",
                "grammar_note": "作为填充词使用，不遵循严格的语法规则，可以放在句首、句中或句尾。",
            },
            "I mean": {
                "meaning": "我的意思是；其实；就是说",
                "chinese_difference": "中文说'我的意思是'、'其实'，英语中的 I mean 更口语化，常用于纠正或进一步解释。",
                "tone_analysis": "I mean 的语气带有一种解释、纠正或补充的意味。它表明说话者想更准确地表达自己的意思。",
                "learning_pitfall": "以前我只会直接表达，后来发现 I mean 在口语中非常有用，可以用来纠正自己说过的话，或者进一步解释。",
                "scene_expansion": "适合日常对话、纠正表达、补充说明，比如'I was like, you know, I mean, it's not that bad.'（我当时就想，我的意思是，也没那么糟糕。）。",
                "grammar_note": "作为填充词使用，通常放在句首或句中。",
            },
            "thing": {
                "meaning": "东西；事情；事物",
                "chinese_difference": "中文说'东西'、'事情'，英语中的 thing 用法非常广泛，可以指代几乎任何事物，这在中文里是不太常见的。",
                "tone_analysis": "thing 的语气非常随意，带有一种模糊指代的意味。在正式写作中最好用更具体的词，但在口语中 thing 是万能词。",
                "learning_pitfall": "以前我总是想用具体的词来指代事物，后来发现 native speaker 在口语中经常用 thing 来泛指，这大大简化了表达。",
                "scene_expansion": "适合日常对话、指代不确定的事物，比如'The thing is...'（问题是...）或者'I have a thing for that.'（我对那个很感兴趣。）。",
                "grammar_note": "作为名词使用，可以指代具体或抽象的事物。",
            },
            "stuff": {
                "meaning": "东西；事物；材料",
                "chinese_difference": "和 thing 类似，中文说'东西'、'材料'，英语中的 stuff 更口语化，通常指一堆不确定的物品或事物。",
                "tone_analysis": "stuff 的语气非常随意，带有一种杂乱或不确定的意味。和 thing 相比，stuff 更常用于指代一堆东西。",
                "learning_pitfall": "以前我分不清 thing 和 stuff 的区别，后来发现 thing 通常指单个事物，stuff 指多个或一堆不确定的事物。",
                "scene_expansion": "适合日常对话、指代一堆物品，比如'Can you help me move this stuff?'（你能帮我搬这些东西吗？）或者'Good stuff!'（好东西！）。",
                "grammar_note": "作为不可数名词使用，虽然是单数形式但指代多个事物。",
            },
            "that's it": {
                "meaning": "就是这样；仅此而已",
                "chinese_difference": "中文说'就是这样'、'仅此而已'，英语中的 that's it 更口语化，常用于结束对话或总结。",
                "tone_analysis": "that's it 的语气带有一种结束或总结的意味。和 that's all 相比，that's it 更简洁，语气更强。",
                "learning_pitfall": "以前我只会说 that's all，后来发现 that's it 在口语中更常用，特别是在结束对话时。",
                "scene_expansion": "适合结束对话、总结内容，比如'That's it for today!'（今天就到这里！）或者'That's it, we're done!'（就这样，我们完成了！）。",
                "grammar_note": "作为固定表达使用，单独成句。",
            },
        }
    
    def get_expression_list(self) -> List[str]:
        """获取知识库中所有表达的列表"""
        return list(self._knowledge.keys())


knowledge_base = ExpressionKnowledgeBase()


def get_knowledge_base() -> ExpressionKnowledgeBase:
    """获取知识库单例"""
    return knowledge_base