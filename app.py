import streamlit as st
import pandas as pd
import requests
import json


#@st.cache_data
def get_league_data(leagueID):
    if not isinstance(leagueID, int):
        leagueID = int(leagueID)
    fpl_league_url = (
        f"https://fantasy.premierleague.com/api/leagues-classic/{leagueID}/standings/"
    )
    respose = requests.get(fpl_league_url)
    fpl_league_respose_json = respose.json()
    league_df = pd.DataFrame(fpl_league_respose_json["standings"]["results"])
    return league_df


st.title("FPL League Dashboard")
st.subheader("Input your league ID to view various statistics")

leagueID = st.number_input("League ID", value=None, placeholder="Type a number...", step=1)
print("leagueID: {}".format(leagueID))
print("type(leagueID): {}".format(type(leagueID)))
render_elements = False
if leagueID is not None:
    render_elements = True
    league_df = get_league_data(leagueID)
else:
    st.info("☝️ Input league ID")

if render_elements:
    st.dataframe(league_df, use_container_width=True)
