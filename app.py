import streamlit as st
import datetime as datetime
import numpy as np
import plotly.express as px
import os
import utils
from league_data import LeagueData

root_dir_path = os.path.dirname(os.path.realpath(__file__))


###################
### Page Config ###
###################


st.set_page_config(
    page_title="FPL stats App",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="auto",
)

sidebar_img = utils.get_img_as_base64(
    root_dir_path + "/data/app/wp11906650-fantasy-premier-league-wallpapers.jpg"
)

background_img = utils.get_img_as_base64(
    root_dir_path + "/data/app/wp2598920-white-wallpaper.jpg"
)


#################
### Constants ###
#################


standings_url_template = (
    "https://fantasy.premierleague.com/api/leagues-classic/{leagueID}/standings/"
)
history_url_template = (
    "https://fantasy.premierleague.com/api/entry/{manager_id}/history/"
)
picks_url_template = (
    "https://fantasy.premierleague.com/api/entry/{manager_id}/event/{gw}/picks/"
)
transfers_url_template = (
    "https://fantasy.premierleague.com/api/entry/{manager_id}/transfers/"
)
bootstrap_static_url = "https://fantasy.premierleague.com/api/bootstrap-static/"
live_url_template = "https://fantasy.premierleague.com/api/event/{gw}/live/"


#################
### Functions ###
#################


def inject_custom_css():
    with open(root_dir_path + "/data/app/CSS/styles.txt") as f:
        css_sheet = str(f.read()).format(
            sidebar_img=sidebar_img, background_img=background_img
        )
        st.markdown(
            """<style>{}</style>""".format(css_sheet),
            unsafe_allow_html=True,
        )
    return None


##################
### App proper ###
##################


def main():
    inject_custom_css()
    st.title("FPL League Dashboard")
    st.subheader("Input your league ID to view various statistics")

    leagueID = st.number_input(
        "League ID",
        value=None,
        placeholder="Type your league ID here and press ↳ENTER",
        step=1,
    )

    render_elements = False
    if leagueID != None:
        render_elements = True
    else:
        st.info(
            "How to find you league ID:  \n"
            "👉 Login to your FPL account  \n"
            "👉 Select the 'Leagues & Cups' tab  \n"
            "👉 Select a league  \n"
            "👉 Copy ID from the URL  \n"
        )

    ##############
    ### Render ###
    ##############

    if render_elements:

        ldo = LeagueData(  # league data object
            leagueID=leagueID,  # type: ignore
            standings_url_template=standings_url_template,
            history_url_template=history_url_template,
            picks_url_template=picks_url_template,
            transfers_url_template=transfers_url_template,
            bootstrap_static_url=bootstrap_static_url,
            live_url_template=live_url_template,
        )

        ### "What if" logic
        what_if_col, gw_select_col, buffer_cols = st.columns([5, 3, 12])
        with what_if_col:
            what_if_on = st.toggle(
                "'What if' mode",
                value=False,
                help="What if you hadn't made those transfers? "
                "To find out, switch on and select the gameweek from which you theoretically stopped making transfers.",
            )
        if what_if_on:
            with gw_select_col:
                what_if_gw = st.number_input(
                    "Gameweek",
                    value=ldo.max_gw - 1,
                    step=1,
                    min_value=1,
                    max_value=ldo.max_gw,
                )

        ### Side bar
        with st.sidebar:
            tab_headers = {
                "tab1": "Summary",
                "tab2": "Season Stats.",
                "tab3": "Team Similarity",
                "tab4": "Team Comparison",
                "tab5": "Transfers",
            }
            st.header("Info...")
            with st.expander(tab_headers["tab1"]):
                st.write(
                    "A convenient summary table of league standings for the current season. "
                    "Not too dissimilar to the summary table on the official app/website."
                )
            with st.expander(tab_headers["tab2"]):
                st.write(
                    "A line graph of various statistics for each manager throughout the current season. "
                    "Pick a parameter to plot and adjust the gameweek range. The graph is interactive too!"
                )
            with st.expander(tab_headers["tab3"]):
                st.write(
                    "Check which managers have had similar team selections for a given gameweek. "
                    "Or, select a range of gameweeks to find the average similarity."
                )
            with st.expander(tab_headers["tab4"]):
                st.write(
                    "Compare team selections of two managers for a given gameweek. "
                    "Captained (c), vice-captained (v), and benched (b) players are considered distinct selections."
                )
            with st.expander(tab_headers["tab5"]):
                st.write(
                    "Ever wondered which players your fellow mangers have transfered? and when? "
                    "Then this graph is for you! Zoom in to see multiple tranfers in a single transaction. "
                    "NOTE: Can only see transfers *after* the gameweek deadline. "
                )

        ### Tabs
        tab1, tab2, tab3, tab4, tab5 = st.tabs(
            [tab_headers[k] for k, v in tab_headers.items()]
        )

        st.dataframe(ldo.players_df)
        with tab1:
            st.header(f"{ldo.league_name}")
            ldo.standings_df = ldo.standings_df.merge(
                ldo.season_stats_df.loc[
                    ldo.season_stats_df["GW"] == ldo.max_gw, ["Manager", "Form"]
                ],
                how="inner",
                on="Manager",
            )
            st.dataframe(
                ldo.standings_df[
                    ["Rank", "Manager", "Team Name", "GW Total", "Total Points", "Form"]
                ].style.format({"Form": "{:.2f}"}, thousands=","),
                use_container_width=True,
                hide_index=True,
            )
        with tab2:
            st.header(f"{ldo.league_name}")
            with st.container(border=True):
                y_axis_option = st.selectbox(
                    "Pick a Parameter to Plot",
                    sorted(
                        [
                            "Points",
                            "Total Points",
                            "Rank",
                            "Overall Rank",
                            "Bank",
                            "Value",
                            "Form",
                            "Transfers",
                            "Transfer Costs",
                            "Points on Bench",
                            "Total Transfers",
                            "Total Transfer Costs",
                            "Total Points on Bench",
                        ]
                    ),
                    index=3,
                )
                gw_range = st.slider(
                    "Select Gameweek Range", 1, ldo.max_gw, (1, ldo.max_gw)
                )
                fig = ldo.make_season_stats_chart(
                    gw_range=gw_range, y_axis_option=y_axis_option
                )
                if y_axis_option in ["Rank", "Overall Rank"]:
                    fig.update_yaxes(autorange="reversed")
                st.plotly_chart(fig, theme="streamlit", use_container_width=True)
        with tab3:
            st.header(f"{ldo.league_name}")

            with st.container(border=True):
                gw_type = st.radio(
                    "Choose Gameweek Selection Type",
                    ["Single Gameweek", "Multiple Gameweeks"],
                    captions=[
                        "Team similarity of a single GW",
                        "Average similarity over multiple GWs",
                    ],
                    horizontal=True,
                )

                if gw_type == "Single Gameweek":
                    gw_range = st.slider(
                        "Select Gameweek Range",
                        1,
                        ldo.max_gw,
                        ldo.max_gw,
                        key="single_gw",
                    )
                    gw_select_indx = list(range((gw_range - 1) * 15, gw_range * 15))
                elif gw_type == "Multiple Gameweeks":
                    gw_range = st.slider(
                        "Select Gameweek Range",
                        1,
                        ldo.max_gw,
                        (1, ldo.max_gw),
                        key="multi_gw",
                    )
                    gw_select_indx = list(
                        range((gw_range[0] - 1) * 15, gw_range[1] * 15)
                    )
                else:
                    gw_select_indx = []

                sim_df = utils.jaccard_sim(ldo.league_picks_df.iloc[gw_select_indx])
                fig = ldo.make_similarity_heatmap(sim_df=sim_df)
                st.plotly_chart(fig, theme="streamlit", use_container_width=True)
        with tab4:
            st.header(f"{ldo.league_name}")
            with st.container(border=True):
                if gw_type == "Single Gameweek":
                    managers = ldo.standings_df["Manager"].values
                    gw_range = st.slider(
                        "Select Gameweek",
                        1,
                        ldo.max_gw,
                        ldo.max_gw,
                        key="single_gw_venn",
                    )
                    col1, col2 = st.columns(2)
                    with col1:
                        manager1 = st.selectbox("Select Manager 1", managers)
                    with col2:
                        manager2 = st.selectbox("Select Manager 2", managers)
                    manager1_set = set(
                        ldo.league_teams_df.loc[
                            (ldo.league_teams_df["Manager"] == str(manager1))
                            & (ldo.league_teams_df["gw"] == int(gw_range)),
                            "player_pick",
                        ]
                    )
                    manager2_set = set(
                        ldo.league_teams_df.loc[
                            (ldo.league_teams_df["Manager"] == str(manager2))
                            & (ldo.league_teams_df["gw"] == int(gw_range)),
                            "player_pick",
                        ]
                    )
                    manager1_players = [
                        s.replace(" (p)", "")
                        for s in manager1_set.difference(manager2_set)
                    ]
                    intersection_players = [
                        s.replace(" (p)", "")
                        for s in manager1_set.intersection(manager2_set)
                    ]
                    manager2_players = [
                        s.replace(" (p)", "")
                        for s in manager2_set.difference(manager1_set)
                    ]
                    words = manager1_players + intersection_players + manager2_players
                    colour1_idx = np.where(managers == manager1)[0][0] % 10
                    colour2_idx = np.where(managers == manager2)[0][0] % 10
                    venn = utils.word_list_venn_diagram(
                        words=words,
                        fontsizes=[10] * len(words),
                        polarities=[-1] * len(manager1_players)
                        + [0] * len(intersection_players)
                        + [1] * len(manager2_players),
                        colour1=px.colors.qualitative.Plotly[colour1_idx],
                        colour2=px.colors.qualitative.Plotly[colour2_idx],
                        scale=1.5,
                    )
                    venn_fig = venn.fig
                    st.pyplot(venn_fig)
        with tab5:
            st.header(f"{ldo.league_name}")
            with st.container(border=True):
                fig = ldo.make_transfers_fig()
                st.plotly_chart(fig, theme="streamlit", use_container_width=True)


if __name__ == "__main__":
    main()
