# 六级练习台

这是一个给大学英语六级备考用的本地网页小工具。直接打开 `index.html` 就能开始练习，不需要安装开发环境。

## 怎么用

1. 双击打开 `index.html`。
2. 先用内置原创示例题试一下选择题、填空题、错题本。
3. 如果要换成自己的题库，点页面右上角“导入题库”，选择一个 JSON 文件。
4. 可以参考 `questions.sample.json` 的格式整理题目。

## 手机上使用

长期使用建议部署成静态网页，见 `DEPLOY.md`。如果题库里包含真题内容，不建议把题库 JSON 放进公开仓库。

## 题库格式

选择题：

```json
{
  "id": "unique-question-id",
  "type": "choice",
  "section": "vocabulary",
  "source": "2025-12 真题或自定义来源",
  "stem": "题干",
  "options": [
    { "key": "A", "text": "选项 A" },
    { "key": "B", "text": "选项 B" },
    { "key": "C", "text": "选项 C" },
    { "key": "D", "text": "选项 D" }
  ],
  "answer": "A",
  "explanation": "为什么选 A，为什么其他选项不对。"
}
```

填空题：

```json
{
  "id": "unique-blank-id",
  "type": "blank",
  "section": "grammar",
  "source": "自定义来源",
  "stem": "No sooner had she entered the classroom _____ the bell rang.",
  "answer": ["than"],
  "explanation": "No sooner ... than ... 是固定结构。"
}
```

`section` 可以用：

- `vocabulary`：词汇辨析
- `reading`：阅读理解
- `grammar`：语法结构
- `cloze`：段落填空

## 关于近五年真题

近五年六级真题通常有版权，不建议把网上来历不明的真题直接复制进公开项目或部署到公网。更稳妥的做法是：

- 自己购买或使用学校/正规渠道提供的真题资料。
- 只在自己电脑上整理成 JSON 练习。
- 如果要公开发布网页，使用原创模拟题、授权题库，或只发布网页代码，不发布真题内容。
