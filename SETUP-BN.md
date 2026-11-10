# Setup (বাংলা)

## ১. GitHub profile repository তৈরি করো

1. https://github.com/new খোলো।
2. Repository name ঠিক `av6r01` দাও।
3. **Public** রাখো।
4. README initialize করার অপশন অন না করলেও হবে, কারণ এই package-এ README.md আছে।
5. Create repository চাপো।

## ২. ZIP-এর ফাইলগুলো upload করো

ZIP extract করে ভেতরের সব ফাইল ও folder (`.github` সহ) `av6r01/av6r01` repository-তে upload করো। GitHub-এর Upload files দিয়ে upload করলে `.github/workflows/update-profile.yml`-ও ঠিক path-এ আছে কি না দেখে নিও। সহজ পদ্ধতি হলো GitHub Desktop দিয়ে repository clone করে extracted files copy-paste করে commit/push করা।

## ৩. Actions permission চালু করো

Repository → Settings → Actions → General → Workflow permissions-এ **Read and write permissions** নির্বাচন করে Save করো। Workflow-এ `contents: write` আছে, কিন্তু repository setting যদি write block করে রাখে, তাহলে commit করতে পারবে না।

## ৪. প্রথমবার চালাও

Repository → Actions → **Update Dynamic GitHub Profile** → Run workflow চাপো। সফল হলে `assets/`-এ পাঁচটি custom SVG card তৈরি হবে এবং README-তেও সেগুলো দেখাবে।

## ৫. পরে কীভাবে আপডেট হবে?

Workflow দিনে চারবার (প্রায় প্রতি ৬ ঘণ্টায়) চলবে, আর তুমি profile repository-তে নতুন commit/push করলেও চলবে। GitHub-এর schedule execution queue-তে কিছুটা দেরি হতে পারে। Public repository-তে ৬০ দিন কোনো activity না থাকলে scheduled workflow auto-disable হতে পারে; তখন Actions tab থেকে পুনরায় enable করা যায়।

## কী কী dynamic?

- Public repository count, stars, followers, forks
- Repository-গুলোর language breakdown
- Top/recent public project cards
- Contribution calendar (GraphQL access পাওয়া গেলে)
- GraphQL না পাওয়া গেলে স্পষ্টভাবে labelled recent-public-events fallback

কোনো paid API বা external image-generation service ব্যবহার করা হয়নি। Script-এ কোনো personal access token hardcode করতে হবে না। GitHub Actions নিজের `GITHUB_TOKEN` ব্যবহার করবে।
