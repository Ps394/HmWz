import pytest

AccountTableParser = pytest.importorskip(
    "html_to_json.export_game_accounts"
).AccountTableParser


def test_extracts_individual_players_and_ignores_labels_and_short_values():
    parser = AccountTableParser()
    parser.feed("""
        <table><thead><tr><th>Discord Username</th><th>Spieler</th></tr></thead>
        <tbody>
          <tr><td><div> user </div><p-tag>MANUELL</p-tag></td>
              <td><span><p-tag><span>First Player</span></p-tag></span>
                  <span><p-tag><span>Second &amp; Player</span></p-tag></span>
                  <span><p-tag>x</p-tag></span></td></tr>
          <tr><td><div>empty</div></td><td><span>-</span></td></tr>
          <tr><td><div>single</div></td><td><p-tag>Only Player</p-tag></td></tr>
          <tr><td><div>short-first</div></td>
              <td><p-tag>x</p-tag><p-tag>Remaining</p-tag></td></tr>
          <tr><td><div> </div></td><td><p-tag>Player</p-tag></td></tr>
        </tbody></table>
    """)
    assert parser.entries == [
        {"discord_username": "user", "players": ["Second & Player"]},
        {"discord_username": "short-first", "players": ["Remaining"]},
    ]
