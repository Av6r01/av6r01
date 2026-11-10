# GitHub-এ পুরো package upload করার নিয়ম

তোমার profile repository: https://github.com/av6r01/av6r01

## সবচেয়ে সহজ পদ্ধতি: GitHub ওয়েবসাইট

1. এই ZIP extract করো।
2. GitHub-এ `av6r01/av6r01` repository খোলো।
3. `Add file` → `Upload files` চাপো।
4. Extract করা folder-এর **ভেতরের সব file ও folder** upload area-তে drag করো। বাইরের `av6r01-dynamic-profile-fixed` folder-টা নয়, তার ভেতরের জিনিসগুলো upload করবে।
5. `.github` folder-টিও অবশ্যই upload করবে। এতে `workflows/update-profile.yml` থাকতে হবে।
6. Commit changes করো।

## Upload শেষে repository-তে এই structure থাকতে হবে

```text
av6r01/
├── README.md
├── .gitignore
├── .github/
│   └── workflows/
│       └── update-profile.yml
├── assets/
│   ├── hero.svg
│   ├── stats.svg
│   ├── languages.svg
│   ├── projects.svg
│   └── activity.svg
└── scripts/
    └── generate_profile.py
```

## Permission ও প্রথম run

1. Repository → Settings → Actions → General.
2. Workflow permissions অংশে `Read and write permissions` নির্বাচন করে Save করো।
3. Actions tab → `Update Dynamic GitHub Profile` → `Run workflow` → `Run workflow`.
4. Run সফল হলে README-র SVG cards actual GitHub data দিয়ে regenerate হবে।

## গুরুত্বপূর্ণ

- README-র image URL-গুলো `raw.githubusercontent.com/av6r01/av6r01/main/assets/...` ব্যবহার করে।
- ZIP-এর `.github` hidden folder না উঠলে Actions workflow পাওয়া যাবে না। Upload করার পর repository-র Code tab-এ `.github/workflows/update-profile.yml` দেখা যাচ্ছে কি না নিশ্চিত করো।
- Default branch যদি `main` না হয়ে অন্য নাম হয়, workflow-র `branches: [main]` এবং raw image URL-এর `/main/` অংশটি সেই branch name দিয়ে বদলাতে হবে।
