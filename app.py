import streamlit as st
import pandas as pd
import requests
import json
import plotly.express as px

col_name_change_dict = {
    "event": "GW",
    "event_total": "GW Total",
    "player_name": "Manager",
    "entry": "ID",
    "entry_name": "Team Name",
}

st.set_page_config(
    page_title="FPL stats App",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="auto",
)


@st.cache_data
def get_league_data(leagueID):
    if not isinstance(leagueID, int):
        leagueID = int(leagueID)
    fpl_league_url = (
        f"https://fantasy.premierleague.com/api/leagues-classic/{leagueID}/standings/"
    )
    respose = requests.get(fpl_league_url)
    fpl_league_respose_json = respose.json()
    league_df = pd.DataFrame(fpl_league_respose_json["standings"]["results"]).rename(
        columns=col_name_change_dict
    )
    return league_df


@st.cache_data
def get_all_mngrs_all_gws_df(league_df):
    all_gws_url_template = (
        "https://fantasy.premierleague.com/api/entry/{manager_id}/history/"
    )
    all_gws_df_list = []
    for i, manager_id in enumerate(league_df["ID"]):
        respose = requests.get(all_gws_url_template.format(manager_id=manager_id))
        all_gws_respose_json = respose.json()
        all_gws_df = pd.DataFrame(all_gws_respose_json["current"])
        all_gws_df["ID"] = manager_id
        all_gws_df["Team Name"] = league_df.loc[i, "Team Name"]
        all_gws_df["Manager"] = league_df.loc[i, "Manager"]
        all_gws_df_list.append(all_gws_df)
    all_mngrs_all_gws_df = pd.concat(all_gws_df_list)
    return all_mngrs_all_gws_df


st.title("FPL League Dashboard")
st.subheader("Input your league ID to view various statistics")

leagueID = st.number_input(
    "League ID", value=None, placeholder="Type your league ID here...", step=1
)

render_elements = False
if leagueID != None:
    render_elements = True
    league_df = get_league_data(leagueID)
else:
    league_df = None
    st.info(
        "How to find you league ID:  \n"
        "👉 Login to your FPL account  \n"
        "👉 Select the 'Leagues & Cups' tab  \n"
        "👉 Select a league  \n"
        "👉 ID is in the URL  \n"
    )

if render_elements:
    with st.sidebar:
        st.header("Info...")
    tab1, tab2, tab3 = st.tabs(["Summary", "Graphs", "Analysis"])
    with tab1:
        st.dataframe(league_df, use_container_width=True)
        all_mngrs_all_gws_df = get_all_mngrs_all_gws_df(league_df)
        st.dataframe(all_mngrs_all_gws_df)
        y_axis_option = st.selectbox(
            "Pick a Parameter to Plot", all_mngrs_all_gws_df.columns.to_list()
        )
        fig = px.line(
            all_mngrs_all_gws_df,
            x="event",
            y=y_axis_option,
            color="Manager",
            markers=True,
        )
        st.plotly_chart(fig, theme="streamlit", use_container_width=True)
