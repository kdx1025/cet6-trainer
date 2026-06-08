# 手机远程访问方案

这个项目是纯静态网页，最适合部署到 GitHub Pages、Vercel 或 Netlify。部署后，你女朋友只需要用手机浏览器打开网址就能练习，不需要和你在同一个 Wi-Fi。

## 推荐方案：GitHub Pages

适合长期免费使用，但免费版通常要用公开仓库。GitHub 官方文档说明：GitHub Free 支持 public repositories 的 Pages；private repositories 发布 Pages 需要 GitHub Pro、Team、Enterprise 等计划。

需要你准备：

- 一个 GitHub 账号
- 一个 GitHub 仓库，例如 `cet6-trainer`
- 仓库开启 Pages，分支选择 `main`，目录选择 `/root`

部署后访问地址通常是：

```text
https://你的用户名.github.io/cet6-trainer/
```

## 备选方案：Vercel

适合最省事部署静态站，也更适合私有仓库部署。

需要你准备：

- 一个 GitHub 账号
- 一个 Vercel 账号
- 在 Vercel 导入这个仓库

构建设置保持默认即可，因为这是静态 HTML，不需要 npm build。

## 本地临时访问

如果你们在同一个 Wi-Fi，可以用电脑临时开服务：

```powershell
python -m http.server 8765 --bind 0.0.0.0
```

然后在手机浏览器打开：

```text
http://你的电脑局域网IP:8765/index.html
```

这个方式只适合临时用，电脑关机或网络变化后就不能访问。

## 题库隐私提醒

如果题库里包含真题内容，不建议公开仓库。更稳妥的方式是：

- 仓库公开时只放网页代码，不放真题 JSON
- 或者仓库设为 private，再用 Vercel/Netlify 的私有仓库部署
- 如果用 GitHub Pages 免费版公开仓库，真题 JSON 也会公开
