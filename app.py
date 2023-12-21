import streamlit as st
import pandas as pd
import requests
import json
import plotly.express as px


@st.cache_data
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


@st.cache_data
def get_all_mngrs_all_gws_df(league_df):
    all_gws_url_template = (
        "https://fantasy.premierleague.com/api/entry/{manager_id}/history/"
    )
    all_gws_df_list = []
    for i, manager_id in enumerate(league_df["entry"]):
        respose = requests.get(all_gws_url_template.format(manager_id=manager_id))
        all_gws_respose_json = respose.json()
        all_gws_df = pd.DataFrame(all_gws_respose_json["current"])
        all_gws_df["entry"] = manager_id
        all_gws_df["entry_name"] = league_df.loc[i, "entry_name"]
        all_gws_df["player_name"] = league_df.loc[i, "player_name"]
        all_gws_df_list.append(all_gws_df)
    all_mngrs_all_gws_df = pd.concat(all_gws_df_list)
    return all_mngrs_all_gws_df


st.title("FPL League Dashboard")
st.subheader("Input your league ID to view various statistics")

leagueID = st.number_input(
    "League ID", value=None, placeholder="Type a number...", step=1
)
render_elements = False
if leagueID is not None:
    render_elements = True
    league_df = get_league_data(leagueID)
else:
    league_df = None
    st.info("☝️ Input league ID")

if render_elements:
    st.dataframe(league_df, use_container_width=True)
    all_mngrs_all_gws_df = get_all_mngrs_all_gws_df(league_df)
    fig = px.line(
        all_mngrs_all_gws_df,
        x="event",
        y="total_points",
        color="player_name",
        markers=True,
    )
    st.plotly_chart(fig)
