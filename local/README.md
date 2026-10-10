# Open this project on your computer

`127.0.0.1` in the cloud session is not your computer. Your browser will refuse that address. Clone this branch into a folder on your machine, then open that folder.

## Connect the folder

```bash
git clone --branch cursor/vave-intelligence-platform-ca7b https://github.com/sri369155/ISearch.git VAVE-Intelligence
```

On Windows PowerShell:

```powershell
git clone --branch cursor/vave-intelligence-platform-ca7b https://github.com/sri369155/ISearch.git $env:USERPROFILE\VAVE-Intelligence
```

In Cursor, choose **File → Open Folder** and select the `VAVE-Intelligence` folder you just created.

## Start it so localhost is your machine

From that folder:

```bash
sh scripts/start-local.sh
```

Then open `http://127.0.0.1:5173` in your own browser.

Sign in with `engineer@vave.local` / `VaveDemo!234`.

PostgreSQL 16 with the `vector` extension must already be running locally. The commands in the repository `README.md` create the `vave` database.

## Load your own files

Put `.xlsx`, `.csv`, `.pdf`, `.docx`, `.txt`, or `.md` files in `data/local`. In the app, open **Import data** and choose **Load from local folder**. Only names inside that folder are accepted.
